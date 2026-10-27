
from audit_dead_letter_reader import DeadLetterReader
from audit_dead_letter_replay_preview import DeadLetterReplayPreview


class DeadLetterReplayService:
    def __init__(self, file_path, retry_service, operation_recorder=None):
        self._reader = DeadLetterReader(file_path)
        self._preview = DeadLetterReplayPreview(file_path)
        self._retry_service = retry_service
        self._operation_recorder = operation_recorder

    def _finish(self, result, actor):
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

        # Write-ahead audit: record intent before execution.
        if self._operation_recorder is not None:
            self._finish({
                "status": "STARTED",
                "event_id": event_id,
                "reason": "REPLAY_EXECUTION_STARTED",
            }, actor)

        try:
            result = self._retry_service.execute(audit)
        except Exception as exc:
            result = {
                "status": "FAILED",
                "event_id": event_id,
                "last_error_type": type(exc).__name__,
                "reason": "REPLAY_EXECUTION_EXCEPTION",
            }

        return self._finish(result, actor)


