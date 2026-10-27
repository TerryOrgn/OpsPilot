
from datetime import datetime

from mysql_job_repository import MySQLJobRepository


NOW = datetime(2026, 10, 24, 12, 0)


class FakeCursor:

    def __init__(self):
        self.executions = []
        self.current_status = None
        self.closed = False

    def execute(self, sql, params):
        self.executions.append((sql, params))
        self.current_status = params[0]

    def fetchall(self):
        data = {
            "FAILED": [
                ("FAIL-001", "FailedJob", "FAILED",
                 datetime(2026, 10, 24, 9, 0)),
                ("FAIL-002", "FailedJob", "FAILED",
                 datetime(2026, 10, 24, 8, 0)),
            ],
            "TIMEOUT": [
                ("TIME-001", "TimeoutJob", "TIMEOUT",
                 datetime(2026, 10, 24, 10, 0)),
            ],
            "RUNNING": [
                ("RUN-001", "RunningJob", "RUNNING",
                 datetime(2026, 10, 24, 11, 0)),
                ("RUN-002", "RunningJob", "RUNNING",
                 datetime(2026, 10, 24, 7, 0)),
            ],
        }

        return data[self.current_status]

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
    partition_by_status=True,
)

jobs = repository.get_recent_jobs()

check("THREE_QUERIES", len(
    connection.fake_cursor.executions
) == 3)

params = [
    item[1]
    for item in connection.fake_cursor.executions
]

check(
    "STATUS_PARAMETERS",
    params == [
        ("FAILED", 100),
        ("TIMEOUT", 100),
        ("RUNNING", 100),
    ],
)

check(
    "SQL_PARAMETERIZED",
    all(
        "WHERE STATUS = %s" in sql
        and "LIMIT %s" in sql
        for sql, _ in connection.fake_cursor.executions
    ),
)

check("TOTAL_ROWS", len(jobs) == 5)

check(
    "FAILED_INCLUDED",
    sum(j["status"] == "FAILED" for j in jobs) == 2,
)

check(
    "TIMEOUT_INCLUDED",
    sum(j["status"] == "TIMEOUT" for j in jobs) == 1,
)

check(
    "RUNNING_INCLUDED",
    sum(j["status"] == "RUNNING" for j in jobs) == 2,
)

check(
    "GLOBAL_ORDER",
    [j["execution_id"] for j in jobs] == [
        "RUN-001",
        "TIME-001",
        "FAIL-001",
        "FAIL-002",
        "RUN-002",
    ],
)

check(
    "DATETIME_SERIALIZED",
    all(isinstance(j["updated_at"], str) for j in jobs),
)

check(
    "NO_DUPLICATES",
    len({j["execution_id"] for j in jobs}) == len(jobs),
)

check(
    "CURSOR_CLOSED",
    connection.fake_cursor.closed,
)

check(
    "CONNECTION_CLOSED",
    connection.closed,
)

try:
    MySQLJobRepository(
        connection_factory=lambda: FakeConnection(),
        partition_by_status="yes",
    )
except ValueError:
    invalid_rejected = True
else:
    invalid_rejected = False

check(
    "INVALID_MODE_REJECTED",
    invalid_rejected,
)

print("[TEST] ALL PASS: MySQL Partitioned Repository")
