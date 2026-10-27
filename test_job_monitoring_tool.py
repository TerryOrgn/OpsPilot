
import json

from job_monitoring_tool import JobMonitoringTool


class FakeJobRepository:

    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = 0

    def get_recent_jobs(self):
        self.calls += 1
        return self.jobs


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


jobs = [
    {
        "execution_id": "EXEC-005",
        "job_name": "MONTH_END_REPORT",
        "status": "FAILED",
        "updated_at": "2026-10-24T10:05:00",
    },
    {
        "execution_id": "EXEC-004",
        "job_name": "DAILY_SYNC",
        "status": "SUCCESS",
        "updated_at": "2026-10-24T10:04:00",
    },
    {
        "execution_id": "EXEC-003",
        "job_name": "DATA_IMPORT",
        "status": "TIMEOUT",
        "updated_at": "2026-10-24T10:03:00",
    },
    {
        "execution_id": "EXEC-002",
        "job_name": "FILE_TRANSFER",
        "status": "RUNNING",
        "updated_at": "2026-10-24T10:02:00",
    },
    {
        "execution_id": "EXEC-001",
        "job_name": "MONTH_END_REPORT",
        "status": "FAILED",
        "updated_at": "2026-10-24T10:01:00",
    },
]


repository = FakeJobRepository(jobs)
tool = JobMonitoringTool(repository)

result = tool.execute()


# 1. Tool identity
check(
    "TOOL_NAME",
    result["tool_name"] == "get_recent_abnormal_jobs",
)

# 2. Schema version
check(
    "SCHEMA_VERSION",
    result["schema_version"] == "1.1",
)

# 3. Abnormal count
check(
    "ABNORMAL_COUNT",
    result["abnormal_count"] == 3,
)

# 4. FAILED included
check(
    "FAILED_INCLUDED",
    any(
        job["status"] == "FAILED"
        for job in result["jobs"]
    ),
)

# 5. TIMEOUT included
check(
    "TIMEOUT_INCLUDED",
    any(
        job["status"] == "TIMEOUT"
        for job in result["jobs"]
    ),
)

# 6. SUCCESS excluded
check(
    "SUCCESS_EXCLUDED",
    all(
        job["status"] != "SUCCESS"
        for job in result["jobs"]
    ),
)

# 7. RUNNING excluded
check(
    "RUNNING_EXCLUDED",
    all(
        job["status"] != "RUNNING"
        for job in result["jobs"]
    ),
)

# 8. Result order preserved
check(
    "ORDER_PRESERVED",
    [
        job["execution_id"]
        for job in result["jobs"]
    ] == [
        "EXEC-005",
        "EXEC-003",
        "EXEC-001",
    ],
)

# 9. Limit applied
limited = tool.execute(limit=2)

check(
    "LIMIT_APPLIED",
    limited["abnormal_count"] == 2
    and len(limited["jobs"]) == 2,
)

# 10. Empty result
empty_tool = JobMonitoringTool(
    FakeJobRepository([])
)

empty_result = empty_tool.execute()

check(
    "EMPTY_RESULT",
    empty_result["abnormal_count"] == 0
    and empty_result["jobs"] == [],
)

# 11. Invalid limit
try:
    tool.execute(limit=0)
except ValueError:
    invalid_limit_rejected = True
else:
    invalid_limit_rejected = False

check(
    "INVALID_LIMIT_REJECTED",
    invalid_limit_rejected,
)

# 12. Boolean limit
try:
    tool.execute(limit=True)
except ValueError:
    boolean_limit_rejected = True
else:
    boolean_limit_rejected = False

check(
    "BOOLEAN_LIMIT_REJECTED",
    boolean_limit_rejected,
)

# 13. Missing repository
try:
    JobMonitoringTool(None)
except ValueError:
    missing_repository_rejected = True
else:
    missing_repository_rejected = False

check(
    "MISSING_REPOSITORY_REJECTED",
    missing_repository_rejected,
)

# 14. JSON compatibility
json.dumps(result)

check(
    "JSON_COMPATIBLE",
    True,
)

# 15. Read-only behavior
check(
    "REPOSITORY_READ_ONLY",
    repository.calls == 2
    and jobs[0]["status"] == "FAILED",
)


print(
    "[TEST] ALL PASS: Job Monitoring Tool"
)
