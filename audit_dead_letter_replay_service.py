
from audit_dead_letter_reader import DeadLetterReader
from audit_dead_letter_replay_preview import DeadLetterReplayPreview
from audit_replay_guard import ReplayConcurrencyGuard
import uuid

class DeadLetterReplayService:

    def __init__(
            self,
            file_path,
            retry_service,
            operation_recorder=None,
            concurrency_guard=None,
            process_guard=None,
    ):
        self._reader = DeadLetterReader(file_path)
        self._preview = DeadLetterReplayPreview(file_path)
        self._retry_service = retry_service
        self._operation_recorder = operation_recorder
        self._concurrency_guard = (
            concurrency_guard
            if concurrency_guard is not None
            else ReplayConcurrencyGuard()
        )
        self._process_guard = process_guard

    def _finish(self, result, actor, replay_attempt_id=None):
        if self._operation_recorder is not None:
            operation = {
                "action": "DEAD_LETTER_REPLAY",
                "event_id": result["event_id"],
                "actor": actor,
                "status": result["status"],
                "attempts": result.get("attempts", 0),
                "reason": result.get("reason"),
                "last_error_type": result.get("last_error_type"),
            }

            if replay_attempt_id is not None:
                operation["replay_attempt_id"] = replay_attempt_id

            self._operation_recorder.record(operation)

        return result

    def replay(self, event_id, approved=False, actor="unknown"):
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        if approved is not True:
            return self._finish({
                "status": "REJECTED",
                "event_id": event_id,
                "reason": "APPROVAL_REQUIRED",
            }, actor)

        if self._operation_recorder is None:
            return {
                "status": "REJECTED",
                "event_id": event_id,
                "reason": "AUDIT_RECORDER_REQUIRED",
            }

        # BO-8J: Reject concurrent replay of the same event.
        if not self._concurrency_guard.try_acquire(event_id):
            return self._finish({
                "status": "REJECTED",
                "event_id": event_id,
                "reason": "REPLAY_ALREADY_IN_PROGRESS",
            }, actor)

        process_token = None
        replay_attempt_id = uuid.uuid4().hex

        try:
            if self._process_guard is not None:

                process_token = self._process_guard.try_acquire(
                    event_id,
                    replay_attempt_id=replay_attempt_id,
                )

                if process_token is None:
                    return self._finish({
                        "status": "REJECTED",
                        "event_id": event_id,
                        "reason": "REPLAY_ALREADY_IN_PROGRESS",
                    }, actor)

            records = self._reader.read_all()
            candidates = self._preview.build()

            matches = [
                record for record in records
                if record["event_id"] == event_id
            ]

            if not matches:
                return self._finish({
                    "status": "REJECTED",
                    "event_id": event_id,
                    "reason": "EVENT_NOT_FOUND",
                }, actor)

            if len(matches) != 1:
                return self._finish({
                    "status": "REJECTED",
                    "event_id": event_id,
                    "reason": "DUPLICATE_EVENT_ID",
                }, actor)

            candidate = next(
                item for item in candidates
                if item["event_id"] == event_id
            )

            if not candidate["replay_eligible"]:
                return self._finish({
                    "status": "REJECTED",
                    "event_id": event_id,
                    "reason": "NOT_ELIGIBLE",
                }, actor)

            audit = dict(matches[0]["audit"])



            self._finish(
                {
                    "status": "STARTED",
                    "event_id": event_id,
                    "reason": "REPLAY_EXECUTION_STARTED",
                },
                actor,
                replay_attempt_id=replay_attempt_id,
            )

            try:
                result = self._retry_service.execute(audit)
            except Exception as exc:
                result = {
                    "status": "FAILED",
                    "event_id": event_id,
                    "last_error_type": type(exc).__name__,
                    "reason": "REPLAY_EXECUTION_EXCEPTION",
                }

            return self._finish(
                result,
                actor,
                replay_attempt_id=replay_attempt_id,
            )

        finally:
            try:
                if process_token is not None:
                    self._process_guard.release(event_id, process_token)
            finally:
                self._concurrency_guard.release(event_id)



