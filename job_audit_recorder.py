
import json


class JobAuditRecorder:
    REQUIRED_FIELDS = {
        "event",
        "tool_name",
        "total_abnormal_count",
        "returned_count",
        "truncated",
        "summary_status",
    }

    OPTIONAL_FIELDS = {"request_id", "event_id"}

    def __init__(self, sink):
        if sink is None or not callable(
            getattr(sink, "write", None)
        ):
            raise ValueError("sink must provide write()")

        self._sink = sink

    def record(self, audit):
        if not isinstance(audit, dict):
            raise ValueError("audit must be a dictionary")

        allowed_fields = self.REQUIRED_FIELDS | self.OPTIONAL_FIELDS

        if (
                not self.REQUIRED_FIELDS.issubset(audit)
                or not set(audit).issubset(allowed_fields)
        ):
            raise ValueError("invalid audit fields")

        if "request_id" in audit:
            request_id = audit["request_id"]

            if (
                    not isinstance(request_id, str)
                    or not request_id.strip()
            ):
                raise ValueError("invalid request_id")

        if "event_id" in audit:
            event_id = audit["event_id"]

            if (
                    not isinstance(event_id, str)
                    or not event_id.strip()
                    or len(event_id) > 64
            ):
                raise ValueError("invalid event_id")

        if audit["event"] != "JOB_MONITORING_SUMMARY":
            raise ValueError("invalid event")

        if audit["tool_name"] != "get_recent_abnormal_jobs":
            raise ValueError("invalid tool_name")

        if audit["summary_status"] != "SUCCESS":
            raise ValueError("invalid summary_status")

        total = audit["total_abnormal_count"]
        returned = audit["returned_count"]
        truncated = audit["truncated"]

        for value in (total, returned):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError("invalid count")

        if not isinstance(truncated, bool):
            raise ValueError("invalid truncated")

        if total < returned:
            raise ValueError("total smaller than returned")

        if truncated != (total > returned):
            raise ValueError("inconsistent truncated")

        # Only the validated, allowlisted fields are serialized.
        payload = json.dumps(
            audit,
            ensure_ascii=False,
            sort_keys=True,
        )

        self._sink.write(payload)

        return True
