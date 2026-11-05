
class ReplayAttemptMatcher:
    @staticmethod
    def match(lock, audit_records):
        attempt_id = lock.get("replay_attempt_id")
        event_id = lock.get("event_id")

        if not isinstance(attempt_id, str) or not attempt_id.strip():
            return {
                "status": "CORRELATION_UNCERTAIN",
                "reason": "LOCK_ATTEMPT_ID_MISSING",
                "records": [],
            }

        if not isinstance(event_id, str) or not event_id.strip():
            return {
                "status": "CORRELATION_UNCERTAIN",
                "reason": "LOCK_EVENT_ID_INVALID",
                "records": [],
            }

        matched = [
            record
            for record in audit_records
            if record.get("event_id") == event_id
            and record.get("replay_attempt_id") == attempt_id
            and record.get("action") == "DEAD_LETTER_REPLAY"
        ]

        if not matched:
            return {
                "status": "CORRELATION_UNCERTAIN",
                "reason": "ATTEMPT_AUDIT_NOT_FOUND",
                "records": [],
            }

        statuses = [record.get("status") for record in matched]

        if statuses == ["STARTED", "SUCCESS"]:
            status = "ATTEMPT_SUCCESS"
        elif statuses == ["STARTED", "FAILED"]:
            status = "ATTEMPT_FAILED"
        elif statuses == ["STARTED"]:
            status = "ATTEMPT_INCOMPLETE"
        else:
            return {
                "status": "CORRELATION_UNCERTAIN",
                "reason": "INVALID_AUDIT_SEQUENCE",
                "records": matched,
            }

        return {
            "status": status,
            "reason": None,
            "records": matched,
        }
