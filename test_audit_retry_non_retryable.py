
from audit_retry_service import AuditRetryService


class InvalidAuditRecorder:
    def __init__(self):
        self.call_count = 0

    def record(self, audit):
        self.call_count += 1
        raise ValueError("Invalid audit data")


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


recorder = InvalidAuditRecorder()

service = AuditRetryService(
    recorder=recorder,
    max_attempts=3,
)

audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
    "event_id": "EVT-BO6B-003",
}

caught_error = None

try:
    service.execute(audit)
except ValueError as exc:
    caught_error = exc

check(
    "VALUE_ERROR_PROPAGATED",
    isinstance(caught_error, ValueError),
)

check(
    "ERROR_MESSAGE_PRESERVED",
    str(caught_error) == "Invalid audit data",
)

check(
    "NO_RETRY_ON_VALUE_ERROR",
    recorder.call_count == 1,
)

print("[TEST] ALL PASS: Non-Retryable Error")
