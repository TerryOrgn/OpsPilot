
class JobMonitoringTool:
    TOOL_NAME = "get_recent_abnormal_jobs"

    ABNORMAL_STATUSES = {"FAILED", "TIMEOUT"}

    def __init__(self, repository):
        if repository is None:
            raise ValueError("repository is required")

        self._repository = repository

    def execute(self, limit=10):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        # The repository provides jobs ordered by
        # UPDATED_AT descending.
        jobs = self._repository.get_recent_jobs()

        if not isinstance(jobs, list):
            raise ValueError(
                "repository must return a list"
            )

        abnormal_jobs = []

        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError(
                    "job must be a dictionary"
                )

            if job.get("status") not in (
                self.ABNORMAL_STATUSES
            ):
                continue

            abnormal_jobs.append({
                "execution_id": job.get("execution_id"),
                "job_name": job.get("job_name"),
                "status": job.get("status"),
                "updated_at": job.get("updated_at"),
            })

            if len(abnormal_jobs) >= limit:
                break

        return {
            "schema_version": "1.0",
            "tool_name": self.TOOL_NAME,
            "abnormal_count": len(abnormal_jobs),
            "jobs": abnormal_jobs,
        }
