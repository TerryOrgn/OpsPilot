
import json

from mysql_audit_sink import MySQLAuditSink


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params):
        self.connection.sql = sql
        self.connection.params = params

        if self.connection.fail_execute:
            raise RuntimeError("simulated insert failure")

    def close(self):
        self.connection.cursor_closed = True


class FakeConnection:
    def __init__(self, fail_execute=False):
        self.fail_execute = fail_execute
        self.sql = None
        self.params = None
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.cursor_closed = False

    def cursor(self):
        return FakeCursor(self)

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
    "request_id": "REQ-BO2A-001",
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 15,
    "returned_count": 10,
    "truncated": True,
    "summary_status": "SUCCESS",
}

payload = json.dumps(audit)


# Case 1: Successful insert
connection = FakeConnection()

sink = MySQLAuditSink(
    connection_factory=lambda: connection
)

sink.write(payload)

check(
    "INSERT_EXECUTED",
    "INSERT INTO AGENT_AUDIT_LOG" in connection.sql,
)

check(
    "PARAMETER_COUNT",
    len(connection.params) == 7,
)

check(
    "REQUEST_ID_MAPPED",
    connection.params[0] == "REQ-BO2A-001",
)

check(
    "COUNTS_MAPPED",
    connection.params[3:5] == (15, 10),
)

check(
    "COMMIT_CALLED",
    connection.committed,
)

check(
    "NO_ROLLBACK_ON_SUCCESS",
    not connection.rolled_back,
)

check(
    "RESOURCES_CLOSED",
    connection.cursor_closed and connection.closed,
)


# Case 2: Insert failure
failed_connection = FakeConnection(
    fail_execute=True
)

failed_sink = MySQLAuditSink(
    connection_factory=lambda: failed_connection
)

error_raised = False

try:
    failed_sink.write(payload)
except RuntimeError:
    error_raised = True

check(
    "INSERT_FAILURE_PROPAGATED",
    error_raised,
)

check(
    "ROLLBACK_CALLED",
    failed_connection.rolled_back,
)

check(
    "NO_COMMIT_ON_FAILURE",
    not failed_connection.committed,
)

check(
    "FAILED_RESOURCES_CLOSED",
    failed_connection.cursor_closed
    and failed_connection.closed,
)


# Case 3: Legacy audit without request_id
legacy_connection = FakeConnection()

legacy_sink = MySQLAuditSink(
    connection_factory=lambda: legacy_connection
)

legacy_audit = dict(audit)
del legacy_audit["request_id"]

legacy_sink.write(json.dumps(legacy_audit))

check(
    "LEGACY_REQUEST_ID_NULL",
    legacy_connection.params[0] is None,
)

check(
    "LEGACY_COMMIT",
    legacy_connection.committed,
)

print("[TEST] ALL PASS: MySQL Audit Sink")
