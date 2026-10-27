
from datetime import datetime

from job_timeout_detector import detect_job_status


class JobMonitoringTool:

    TOOL_NAME = "get_recent_abnormal_jobs"
    ABNORMAL_STATUSES = {"FAILED", "TIMEOUT"}

    def __init__(
        self,
        repository,
        enable_timeout_detection=False,
        now_provider=None,
    ):
        if repository is None:
            raise ValueError("repository is required")

        self._repository = repository
        self._enable_timeout_detection = enable_timeout_detection
        self._now_provider = now_provider or datetime.now

    def execute(self, limit=10):
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        jobs = self._repository.get_recent_jobs()

        if not isinstance(jobs, list):
            raise ValueError(
                "repository must return a list"
            )

        abnormal_jobs = []
        total_abnormal_count = 0

        now = (
            self._now_provider()
            if self._enable_timeout_detection
            else None
        )

        for job in jobs:
            if not isinstance(job, dict):
                raise ValueError(
                    "job must be a dictionary"
                )

            original_status = job.get("status")
            detected_status = original_status

            if self._enable_timeout_detection:
                detected_status = detect_job_status(
                    job,
                    now=now,
                )

            if detected_status not in self.ABNORMAL_STATUSES:
                continue

            # Count all abnormalities in the fetched candidates.
            total_abnormal_count += 1

            # Keep response details bounded by limit.
            if len(abnormal_jobs) >= limit:
                continue

            item = {
                "execution_id": job.get("execution_id"),
                "job_name": job.get("job_name"),
                "status": detected_status,
                "updated_at": job.get("updated_at"),
            }

            if self._enable_timeout_detection:
                item["original_status"] = original_status
                item["detected_status"] = detected_status

            abnormal_jobs.append(item)

        returned_count = len(abnormal_jobs)

        return {
            "schema_version": "1.1",
            "tool_name": self.TOOL_NAME,

            # Legacy field: number of returned records.
            "abnormal_count": returned_count,

            # New statistics.
            "total_abnormal_count": total_abnormal_count,
            "returned_count": returned_count,
            "truncated": total_abnormal_count > returned_count,

            "jobs": abnormal_jobs,
        }
