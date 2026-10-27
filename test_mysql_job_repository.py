
from datetime import datetime

from mysql_job_repository import MySQLJobRepository
from job_monitoring_tool import JobMonitoringTool


class FakeCursor:

    def __init__(self):
        self.sql = None
        self.params = None
        self.closed = False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return [
            (
                "EXEC-003",
                "MONTH_END",
                "FAILED",
                datetime(2026, 10, 24, 10, 3),
            ),
            (
                "EXEC-002",
                "DAILY_SYNC",
                "SUCCESS",
                datetime(2026, 10, 24, 10, 2),
            ),
            (
                "EXEC-001",
                "DATA_IMPORT",
                "TIMEOUT",
                datetime(2026, 10, 24, 10, 1),
            ),
        ]

    def close(self):
        self.closed = True


class FakeConnection:

    def __init__(self):
        self.fake_cursor = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


connection = FakeConnection()

repository = MySQLJobRepository(
    connection_factory=lambda: connection,
    fetch_limit=100,
)

jobs = repository.get_recent_jobs()

check(
    "ROWS_RETURNED",
    len(jobs) == 3,
)

check(
    "FIELD_MAPPING",
    jobs[0]["execution_id"] == "EXEC-003",
)

check(
    "DATETIME_SERIALIZED",
    jobs[0]["updated_at"]
    == "2026-10-24T10:03:00",
)

check(
    "PARAMETERIZED_LIMIT",
    connection.fake_cursor.params == (100,),
)

check(
    "ORDER_BY_UPDATED_AT",
    "ORDER BY UPDATED_AT DESC"
    in connection.fake_cursor.sql,
)

check(
    "SELECT_ONLY",
    connection.fake_cursor.sql
    .strip()
    .upper()
    .startswith("SELECT"),
)

check(
    "CURSOR_CLOSED",
    connection.fake_cursor.closed,
)

check(
    "CONNECTION_CLOSED",
    connection.closed,
)


# Integration with existing JobMonitoringTool
connection2 = FakeConnection()

repository2 = MySQLJobRepository(
    connection_factory=lambda: connection2
)

tool = JobMonitoringTool(repository2)
result = tool.execute(limit=2)

check(
    "TOOL_INTEGRATION",
    result["abnormal_count"] == 2,
)

check(
    "SUCCESS_EXCLUDED",
    all(
        job["status"] != "SUCCESS"
        for job in result["jobs"]
    ),
)


# Invalid configuration
try:
    MySQLJobRepository(
        connection_factory=None
    )
except ValueError:
    invalid_factory = True
else:
    invalid_factory = False

check(
    "INVALID_FACTORY_REJECTED",
    invalid_factory,
)

try:
    MySQLJobRepository(
        connection_factory=lambda: FakeConnection(),
        fetch_limit=0,
    )
except ValueError:
    invalid_limit = True
else:
    invalid_limit = False

check(
    "INVALID_FETCH_LIMIT_REJECTED",
    invalid_limit,
)


print(
    "[TEST] ALL PASS: MySQL JOB Repository"
)
