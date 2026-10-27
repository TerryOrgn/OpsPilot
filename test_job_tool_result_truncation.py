
from job_monitoring_tool import JobMonitoringTool


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


# 模拟 Repository 返回 15 条记录
# 前 12 条为 FAILED，后 3 条为 SUCCESS
jobs = []

for i in range(12):
    jobs.append({
        "execution_id": f"FAIL-{i:03d}",
        "job_name": "MonthEndJob",
        "status": "FAILED",
        "updated_at": f"2026-10-24T10:{59-i:02d}:00",
    })

for i in range(3):
    jobs.append({
        "execution_id": f"OK-{i:03d}",
        "job_name": "DailyJob",
        "status": "SUCCESS",
        "updated_at": f"2026-10-24T09:{59-i:02d}:00",
    })


repository = FakeRepository(jobs)

tool = JobMonitoringTool(
    repository=repository,
)

result = tool.execute(limit=10)

returned_jobs = result["jobs"]

all_abnormal_jobs = [
    job for job in jobs
    if job["status"] in {"FAILED", "TIMEOUT"}
]

returned_ids = {
    job["execution_id"]
    for job in returned_jobs
}

missing_ids = {
    job["execution_id"]
    for job in all_abnormal_jobs
} - returned_ids


check("REPOSITORY_TOTAL", len(jobs) == 15)

check(
    "ACTUAL_ABNORMAL_COUNT",
    len(all_abnormal_jobs) == 12,
)

check(
    "TOOL_RETURNED_COUNT",
    len(returned_jobs) == 10,
)

check(
    "REPORTED_ABNORMAL_COUNT",
    result["abnormal_count"] == 10,
)

check(
    "TWO_ABNORMAL_JOBS_MISSING",
    len(missing_ids) == 2,
)

check(
    "MISSING_IDS_CORRECT",
    missing_ids == {"FAIL-010", "FAIL-011"},
)

check(
    "RETURNED_ALL_FAILED",
    all(
        job["status"] == "FAILED"
        for job in returned_jobs
    ),
)

check(
    "REPOSITORY_CALLED_ONCE",
    repository.call_count == 1,
)

print("[TEST] REPOSITORY_TOTAL=", len(jobs))
print(
    "[TEST] ACTUAL_ABNORMAL_COUNT=",
    len(all_abnormal_jobs),
)
print("[TEST] TOOL_RETURNED_COUNT=", len(returned_jobs))
print("[TEST] MISSING_ABNORMAL_IDS=", sorted(missing_ids))

print("[TEST] ALL PASS: Tool Result Truncation Reproduced")
