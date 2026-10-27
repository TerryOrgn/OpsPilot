
from audit_retry_service import AuditRetryService


class FlakyRecorder:
    def __init__(self):
        self.calls = []
        self.successful_writes = []

    def record(self, audit):
        self.calls.append(dict(audit))

        if len(self.calls) == 1:
            raise ConnectionError(
                "Simulated temporary database failure"
            )

        self.successful_writes.append(dict(audit))
        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


recorder = FlakyRecorder()

service = AuditRetryService(
    recorder=recorder,
    max_attempts=2,
)

audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
    "request_id": "REQ-BO6B-001",
    "event_id": "EVT-BO6B-001",
}

result = service.execute(audit)

check(
    "RETRY_SUCCESS",
    result["status"] == "SUCCESS",
)

check(
    "TWO_ATTEMPTS",
    result["attempts"] == 2,
)

check(
    "RECORDER_CALLED_TWICE",
    len(recorder.calls) == 2,
)

check(
    "SAME_EVENT_ID",
    recorder.calls[0]["event_id"]
    == recorder.calls[1]["event_id"],
)

check(
    "EVENT_ID_MATCH",
    result["event_id"] == audit["event_id"],
)

check(
    "SAME_AUDIT_PAYLOAD",
    recorder.calls[0] == recorder.calls[1],
)

check(
    "ONE_SUCCESSFUL_WRITE",
    len(recorder.successful_writes) == 1,
)

check(
    "ORIGINAL_AUDIT_UNCHANGED",
    audit["event_id"] == "EVT-BO6B-001",
)

print("[TEST] ALL PASS: Audit Retry Service")
