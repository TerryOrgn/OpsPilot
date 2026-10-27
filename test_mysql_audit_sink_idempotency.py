
import json

from mysql.connector import IntegrityError

from mysql_audit_sink import MySQLAuditSink


class FakeCursor:
    def __init__(self, duplicate=False):
        self.duplicate = duplicate
        self.execute_count = 0
        self.closed = False

    def execute(self, sql, params):
        self.execute_count += 1

        if self.duplicate:
            raise IntegrityError(
                msg=(
                    "Duplicate entry 'EVT-001' "
                    "for key 'agent_audit_log.UK_AUDIT_EVENT_ID'"
                ),
                errno=1062,
            )

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, duplicate=False):
        self.cursor_instance = FakeCursor(duplicate)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


audit = {
    "event_id": "EVT-001",
    "request_id": "REQ-001",
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
}

payload = json.dumps(audit)


# Case 1: 正常写入
normal = FakeConnection()
sink = MySQLAuditSink(lambda: normal)

sink.write(payload)

check("NORMAL_COMMITTED", normal.committed)
check("NORMAL_CLOSED", normal.closed)
check("NORMAL_CURSOR_CLOSED", normal.cursor_instance.closed)


# Case 2: 相同 EVENT_ID 重复写入
duplicate = FakeConnection(duplicate=True)
sink = MySQLAuditSink(lambda: duplicate)

sink.write(payload)

check("DUPLICATE_ROLLBACK", duplicate.rolled_back)
check("DUPLICATE_NO_COMMIT", not duplicate.committed)
check("DUPLICATE_CONNECTION_CLOSED", duplicate.closed)
check("DUPLICATE_CURSOR_CLOSED", duplicate.cursor_instance.closed)


print("[TEST] ALL PASS: Audit Sink Idempotency")
