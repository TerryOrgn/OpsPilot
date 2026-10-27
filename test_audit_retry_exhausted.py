
from audit_retry_service import AuditRetryService


class AlwaysFailRecorder:
    def __init__(self):
        self.calls = []

    def record(self, audit):
        self.calls.append(dict(audit))
        raise ConnectionError("Database unavailable")


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


recorder = AlwaysFailRecorder()
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
    "request_id": "REQ-BO6B-002",
    "event_id": "EVT-BO6B-002",
}

result = service.execute(audit)

check(
    "FINAL_STATUS_FAILED",
    result["status"] == "FAILED",
)

check(
    "EXACTLY_TWO_ATTEMPTS",
    result["attempts"] == 2,
)

check(
    "NO_EXTRA_RETRIES",
    len(recorder.calls) == 2,
)

check(
    "SAME_EVENT_ID",
    all(
        call["event_id"] == "EVT-BO6B-002"
        for call in recorder.calls
    ),
)

check(
    "ORIGINAL_AUDIT_UNCHANGED",
    audit["event_id"] == "EVT-BO6B-002",
)

print("[TEST] ALL PASS: Retry Exhausted")
