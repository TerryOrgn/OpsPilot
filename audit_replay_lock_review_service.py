
from audit_replay_lock_inspector import ReplayLockInspector
from audit_replay_operation_reader import ReplayOperationReader
from audit_replay_attempt_matcher import ReplayAttemptMatcher


class ReplayLockReviewService:
    def __init__(self, db_path, operation_path,
                 stale_after_seconds=1800):
        self._inspector = ReplayLockInspector(
            db_path,
            stale_after_seconds=stale_after_seconds,
        )
        self._reader = ReplayOperationReader(operation_path)

    def review(self):
        locks = self._inspector.list_active_locks()

        if not locks:
            return []

        # Fail closed if audit data cannot be read or validated.
        records = self._reader.read_all()

        results = []

        for lock in locks:
            match = ReplayAttemptMatcher.match(lock, records)

            results.append({
                "event_id": lock["event_id"],
                "replay_attempt_id": lock.get(
                    "replay_attempt_id"
                ),
                "lock_status": lock["status"],
                "age_seconds": lock["age_seconds"],
                "audit_status": match["status"],
                "audit_reason": match["reason"],
                "recommendation": "MANUAL_REVIEW_REQUIRED",
            })

        return results
    