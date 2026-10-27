
from datetime import datetime, timedelta

from job_monitoring_tool import JobMonitoringTool


NOW = datetime(2026, 10, 24, 12, 0, 0)


class FakeRepository:

    def __init__(self):
        self.calls = 0
        self.jobs = [
            {
                "execution_id": "EXEC-001",
                "job_name": "RunningTimeout",
                "status": "RUNNING",
                "updated_at": NOW - timedelta(minutes=60),
            },
            {
                "execution_id": "EXEC-002",
                "job_name": "RunningNormal",
                "status": "RUNNING",
                "updated_at": NOW - timedelta(minutes=10),
            },
            {
                "execution_id": "EXEC-003",
                "job_name": "FailedJob",
                "status": "FAILED",
                "updated_at": NOW - timedelta(minutes=20),
            },
            {
                "execution_id": "EXEC-004",
                "job_name": "SuccessJob",
                "status": "SUCCESS",
                "updated_at": NOW - timedelta(minutes=5),
            },
            {
                "execution_id": "EXEC-005",
                "job_name": "AlreadyTimeout",
                "status": "TIMEOUT",
                "updated_at": NOW - timedelta(minutes=90),
            },
        ]

    def get_recent_jobs(self):
        self.calls += 1
        return self.jobs


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


repository = FakeRepository()

tool = JobMonitoringTool(
    repository=repository,
    enable_timeout_detection=True,
    now_provider=lambda: NOW,
)

result = tool.execute(limit=10)
jobs = result["jobs"]

check(
    "ABNORMAL_COUNT",
    result["abnormal_count"] == 3,
)

check(
    "RUNNING_TIMEOUT_DETECTED",
    jobs[0]["status"] == "TIMEOUT",
)

check(
    "ORIGINAL_STATUS_PRESERVED",
    jobs[0]["original_status"] == "RUNNING",
)

check(
    "DETECTED_STATUS_CORRECT",
    jobs[0]["detected_status"] == "TIMEOUT",
)

check(
    "NORMAL_RUNNING_EXCLUDED",
    all(
        j["execution_id"] != "EXEC-002"
        for j in jobs
    ),
)

check(
    "FAILED_PRESERVED",
    jobs[1]["status"] == "FAILED",
)

check(
    "EXISTING_TIMEOUT_PRESERVED",
    jobs[2]["status"] == "TIMEOUT",
)

check(
    "SUCCESS_EXCLUDED",
    all(
        j["execution_id"] != "EXEC-004"
        for j in jobs
    ),
)

check(
    "REPOSITORY_CALLED_ONCE",
    repository.calls == 1,
)

check(
    "DATABASE_STATUS_UNCHANGED",
    repository.jobs[0]["status"] == "RUNNING",
)


# Backward compatibility
legacy_tool = JobMonitoringTool(
    repository=FakeRepository()
)

legacy_result = legacy_tool.execute(limit=10)

check(
    "LEGACY_ABNORMAL_COUNT",
    legacy_result["abnormal_count"] == 2,
)

check(
    "LEGACY_NO_NEW_FIELDS",
    all(
        "original_status" not in j
        for j in legacy_result["jobs"]
    ),
)

print(
    "[TEST] ALL PASS: "
    "JOB Monitoring Timeout Integration"
)
