
from datetime import datetime, timedelta

from job_monitoring_tool import JobMonitoringTool


NOW = datetime(2026, 10, 25, 12, 0, 0)


class FakeRepository:
    def __init__(self, jobs):
        self.jobs = jobs
        self.call_count = 0

    def get_recent_jobs(self):
        self.call_count += 1
        return self.jobs


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


jobs = []

# 12 条超时 RUNNING：均已运行超过 30 分钟
for i in range(12):
    jobs.append({
        "execution_id": f"RUN-{i:03d}",
        "job_name": "MonthEndJob",
        "status": "RUNNING",
        "updated_at": NOW - timedelta(minutes=40 + i),
    })

# 3 条 FAILED
for i in range(3):
    jobs.append({
        "execution_id": f"FAIL-{i:03d}",
        "job_name": "DailyJob",
        "status": "FAILED",
        "updated_at": NOW - timedelta(minutes=60 + i),
    })

# 2 条正常 RUNNING
for i in range(2):
    jobs.append({
        "execution_id": f"NORMAL-{i:03d}",
        "job_name": "NormalJob",
        "status": "RUNNING",
        "updated_at": NOW - timedelta(minutes=5 + i),
    })

# 3 条 SUCCESS
for i in range(3):
    jobs.append({
        "execution_id": f"OK-{i:03d}",
        "job_name": "SuccessJob",
        "status": "SUCCESS",
        "updated_at": NOW - timedelta(minutes=10 + i),
    })


repository = FakeRepository(jobs)

tool = JobMonitoringTool(
    repository=repository,
    enable_timeout_detection=True,
    now_provider=lambda: NOW,
)

result = tool.execute(limit=10)

returned_jobs = result["jobs"]


check("CANDIDATE_COUNT", len(jobs) == 20)

check(
    "TOTAL_ABNORMAL_COUNT",
    result["total_abnormal_count"] == 15,
)

check(
    "RETURNED_COUNT",
    result["returned_count"] == 10,
)

check(
    "LEGACY_ABNORMAL_COUNT",
    result["abnormal_count"] == 10,
)

check(
    "TRUNCATED_TRUE",
    result["truncated"] is True,
)

check(
    "RETURNED_TIMEOUT",
    sum(
        job["status"] == "TIMEOUT"
        for job in returned_jobs
    ) == 10,
)

check(
    "ORIGINAL_RUNNING_PRESERVED",
    all(
        job["original_status"] == "RUNNING"
        for job in returned_jobs
    ),
)

check(
    "DETECTED_TIMEOUT",
    all(
        job["detected_status"] == "TIMEOUT"
        for job in returned_jobs
    ),
)

check(
    "NO_NORMAL_RUNNING",
    all(
        job["execution_id"] not in {
            "NORMAL-000",
            "NORMAL-001",
        }
        for job in returned_jobs
    ),
)

check(
    "REPOSITORY_CALLED_ONCE",
    repository.call_count == 1,
)

check(
    "DATABASE_STATE_UNCHANGED",
    all(
        job["status"] == "RUNNING"
        for job in jobs
        if job["execution_id"].startswith("RUN-")
    ),
)

print("[TEST] CANDIDATES=", len(jobs))
print("[TEST] TOTAL_ABNORMAL=", result["total_abnormal_count"])
print("[TEST] RETURNED=", result["returned_count"])
print("[TEST] TRUNCATED=", result["truncated"])
print("[TEST] ALL PASS: Timeout Truncation Integration")
