
class AuditQueueAdapter:
    def __init__(self, audit_queue):
        if not callable(
            getattr(audit_queue, "submit", None)
        ):
            raise ValueError(
                "audit_queue must provide submit()"
            )

        self._queue = audit_queue

    def record(self, audit):
        result = self._queue.submit(audit)

        if not isinstance(result, dict):
            raise ValueError(
                "Invalid audit queue result"
            )

        status = result.get("status")

        if status == "QUEUED":
            return "QUEUED"

        if status == "REJECTED":
            return "REJECTED"

        raise ValueError(
            "Unexpected audit queue status"
        )
