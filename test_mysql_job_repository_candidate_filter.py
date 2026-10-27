
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
                "EXEC-006",
                "FailedJob",
                "FAILED",
                datetime(2026, 10, 24, 10, 6),
            ),
            (
                "EXEC-005",
                "RunningJob",
                "RUNNING",
                datetime(2026, 10, 24, 10, 5),
            ),
            (
                "EXEC-004",
                "TimeoutJob",
                "TIMEOUT",
                datetime(2026, 10, 24, 10, 4),
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
    print(f"[TEST] {name}=PASS")


connection = FakeConnection()

repository = MySQLJobRepository(
    connection_factory=lambda: connection,
    fetch_limit=100,
)

jobs = repository.get_recent_jobs()

normalized_sql = " ".join(
    connection.fake_cursor.sql.upper().split()
)

check(
    "SELECT_ONLY",
    normalized_sql.startswith("SELECT"),
)

check(
    "FAILED_FILTERED_IN_SQL",
    "'FAILED'" in normalized_sql,
)

check(
    "TIMEOUT_FILTERED_IN_SQL",
    "'TIMEOUT'" in normalized_sql,
)

check(
    "RUNNING_FILTERED_IN_SQL",
    "'RUNNING'" in normalized_sql,
)

check(
    "SUCCESS_NOT_IN_FILTER",
    "'SUCCESS'" not in normalized_sql,
)

check(
    "WHERE_STATUS_FILTER",
    "WHERE STATUS IN" in normalized_sql,
)

check(
    "ORDER_PRESERVED",
    "ORDER BY UPDATED_AT DESC, EXECUTION_ID DESC"
    in normalized_sql,
)

check(
    "PARAMETERIZED_LIMIT",
    connection.fake_cursor.params == (100,),
)

check(
    "ROWS_RETURNED",
    len(jobs) == 3,
)

check(
    "RUNNING_RETAINED_AS_CANDIDATE",
    any(j["status"] == "RUNNING" for j in jobs),
)

check(
    "CURSOR_CLOSED",
    connection.fake_cursor.closed,
)

check(
    "CONNECTION_CLOSED",
    connection.closed,
)


# Verify backward-compatible JobMonitoringTool behavior.
connection2 = FakeConnection()

repository2 = MySQLJobRepository(
    connection_factory=lambda: connection2,
)

tool = JobMonitoringTool(repository=repository2)
result = tool.execute(limit=10)

check(
    "LEGACY_ABNORMAL_COUNT",
    result["abnormal_count"] == 2,
)

check(
    "LEGACY_RUNNING_EXCLUDED",
    all(
        j["status"] != "RUNNING"
        for j in result["jobs"]
    ),
)

print(
    "[TEST] ALL PASS: "
    "MySQL Candidate Filter"
)
