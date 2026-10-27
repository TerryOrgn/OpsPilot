
from mysql.connector import errors
from audit_retry_service import AuditRetryService


class FlakyMySQLRecorder:
    def __init__(self):
        self.calls = []

    def record(self, audit):
        self.calls.append(dict(audit))

        if len(self.calls) == 1:
            raise errors.OperationalError(
                errno=2013,
                msg="Lost connection to MySQL server",
            )

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
    "event_id": "EVT-BO6D-001",
}

recorder = FlakyMySQLRecorder()

service = AuditRetryService(
    recorder=recorder,
    max_attempts=2,
)

result = service.execute(audit)

check(
    "MYSQL_RETRY_SUCCESS",
    result["status"] == "SUCCESS",
)

check(
    "MYSQL_TWO_ATTEMPTS",
    result["attempts"] == 2,
)

check(
    "MYSQL_SAME_EVENT_ID",
    recorder.calls[0]["event_id"]
    == recorder.calls[1]["event_id"],
)

check(
    "MYSQL_SAME_PAYLOAD",
    recorder.calls[0] == recorder.calls[1],
)

print("[TEST] ALL PASS: MySQL Retry Integration")
