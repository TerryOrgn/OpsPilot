
from mysql.connector.errors import OperationalError

from audit_retry_service import AuditRetryService


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


AUDIT = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
    "event_id": "EVT-BO6G-001",
}


class FailedMySQLRecorder:
    def __init__(self):
        self.calls = 0

    def record(self, audit):
        self.calls += 1
        raise OperationalError(
            errno=2013,
            msg="Lost connection to MySQL server",
        )


# 场景一：MySQL 故障持续存在，重试耗尽
recorder = FailedMySQLRecorder()
sleep_calls = []

service = AuditRetryService(
    recorder=recorder,
    max_attempts=3,
    sleep_fn=sleep_calls.append,
)

result = service.execute(AUDIT)

check(
    "MYSQL_FINAL_FAILED",
    result["status"] == "FAILED",
)

check(
    "MYSQL_ATTEMPTS",
    result["attempts"] == 3
    and recorder.calls == 3,
)

check(
    "MYSQL_ERROR_TYPE",
    result["last_error_type"] == "OperationalError",
)

check(
    "MYSQL_ERROR_CODE",
    result["last_error_code"] == 2013,
)

check(
    "MYSQL_EVENT_ID_PRESERVED",
    result["event_id"] == "EVT-BO6G-001",
)

check(
    "MYSQL_BACKOFF_PRESERVED",
    sleep_calls == [1.0, 2.0],
)

check(
    "NO_SENSITIVE_ERROR_MESSAGE",
    "last_error_message" not in result
    and "Lost connection" not in str(result),
)


# 场景二：普通 ConnectionError 没有 MySQL 错误码
class FailedConnectionRecorder:
    def record(self, audit):
        raise ConnectionError("Temporary connection failure")


service = AuditRetryService(
    recorder=FailedConnectionRecorder(),
    max_attempts=1,
    sleep_fn=lambda seconds: None,
)

result = service.execute(AUDIT)

check(
    "CONNECTION_ERROR_TYPE",
    result["last_error_type"] == "ConnectionError",
)

check(
    "CONNECTION_ERROR_CODE_NONE",
    result["last_error_code"] is None,
)


# 场景三：成功时不附加失败诊断字段
class SuccessRecorder:
    def record(self, audit):
        return True


service = AuditRetryService(
    recorder=SuccessRecorder(),
    max_attempts=2,
    sleep_fn=lambda seconds: None,
)

result = service.execute(AUDIT)

check(
    "SUCCESS_STATUS",
    result["status"] == "SUCCESS",
)

check(
    "SUCCESS_NO_ERROR_FIELDS",
    "last_error_type" not in result
    and "last_error_code" not in result,
)

print("[TEST] ALL PASS: Audit Retry Diagnostics")
