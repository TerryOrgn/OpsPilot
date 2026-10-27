
from audit_retry_service import AuditRetryService


class FlakyRecorder:
    def __init__(self, failures_before_success):
        self.failures_before_success = failures_before_success
        self.calls = []

    def record(self, audit):
        self.calls.append(dict(audit))

        if len(self.calls) <= self.failures_before_success:
            raise ConnectionError("Temporary DB failure")

        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
    "event_id": "EVT-BO6F-001",
}


# 场景一：失败三次，第四次成功
sleep_calls = []
recorder = FlakyRecorder(failures_before_success=3)

service = AuditRetryService(
    recorder=recorder,
    max_attempts=4,
    base_delay=1,
    max_delay=8,
    sleep_fn=sleep_calls.append,
)

result = service.execute(audit)

check(
    "RETRY_SUCCESS",
    result["status"] == "SUCCESS",
)

check(
    "FOUR_ATTEMPTS",
    result["attempts"] == 4,
)

check(
    "EXPONENTIAL_DELAYS",
    sleep_calls == [1, 2, 4],
)

check(
    "SAME_EVENT_ID",
    all(
        call["event_id"] == "EVT-BO6F-001"
        for call in recorder.calls
    ),
)


# 场景二：首次成功，不等待
sleep_calls = []
recorder = FlakyRecorder(failures_before_success=0)

service = AuditRetryService(
    recorder=recorder,
    max_attempts=3,
    sleep_fn=sleep_calls.append,
)

result = service.execute(audit)

check(
    "IMMEDIATE_SUCCESS",
    result["status"] == "SUCCESS"
    and result["attempts"] == 1,
)

check(
    "NO_SLEEP_ON_SUCCESS",
    sleep_calls == [],
)


# 场景三：达到最大尝试次数，不额外等待
sleep_calls = []
recorder = FlakyRecorder(failures_before_success=10)

service = AuditRetryService(
    recorder=recorder,
    max_attempts=3,
    sleep_fn=sleep_calls.append,
)

result = service.execute(audit)

check(
    "EXHAUSTED_STATUS",
    result["status"] == "FAILED"
    and result["attempts"] == 3,
)

check(
    "NO_SLEEP_AFTER_FINAL_FAILURE",
    sleep_calls == [1, 2],
)


# 场景四：不可重试异常，不等待
class InvalidRecorder:
    def record(self, audit):
        raise ValueError("Invalid audit")


sleep_calls = []

service = AuditRetryService(
    recorder=InvalidRecorder(),
    max_attempts=3,
    sleep_fn=sleep_calls.append,
)

caught = None

try:
    service.execute(audit)
except ValueError as exc:
    caught = exc

check(
    "NON_RETRYABLE_PROPAGATED",
    isinstance(caught, ValueError),
)

check(
    "NO_SLEEP_ON_NON_RETRYABLE",
    sleep_calls == [],
)

print("[TEST] ALL PASS: Audit Retry Backoff")
