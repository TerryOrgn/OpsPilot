
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
tool = JobMonitoringTool(repository=repository)

result = tool.execute(limit=10)


check(
    "SCHEMA_VERSION",
    result["schema_version"] == "1.1",
)

check(
    "TOTAL_ABNORMAL_COUNT",
    result["total_abnormal_count"] == 12,
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
    "JOBS_LENGTH",
    len(result["jobs"]) == 10,
)

check(
    "FIRST_TEN_PRESERVED",
    [
        job["execution_id"]
        for job in result["jobs"]
    ] == [
        f"FAIL-{i:03d}"
        for i in range(10)
    ],
)

check(
    "REPOSITORY_CALLED_ONCE",
    repository.call_count == 1,
)


# A second scenario: no truncation.
small_repository = FakeRepository(jobs[:3])
small_tool = JobMonitoringTool(
    repository=small_repository,
)

small_result = small_tool.execute(limit=10)

check(
    "SMALL_TOTAL",
    small_result["total_abnormal_count"] == 3,
)

check(
    "SMALL_RETURNED",
    small_result["returned_count"] == 3,
)

check(
    "TRUNCATED_FALSE",
    small_result["truncated"] is False,
)

print("[TEST] TOTAL_ABNORMAL=", result["total_abnormal_count"])
print("[TEST] RETURNED=", result["returned_count"])
print("[TEST] TRUNCATED=", result["truncated"])

print("[TEST] ALL PASS: Tool Truncation Metadata")
