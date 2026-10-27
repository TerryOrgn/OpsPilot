
from datetime import datetime, timedelta


MAX_DURATION_SECONDS = 1800


def detect_job_status(job, now=None):
    if now is None:
        now = datetime.now()

    status = job["status"]

    if status != "RUNNING":
        return status

    updated_at = job["updated_at"]

    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(
            updated_at
        )

    if updated_at > now:
        raise ValueError(
            "JOB start time cannot be in the future"
        )

    duration = (now - updated_at).total_seconds()

    if duration >= MAX_DURATION_SECONDS:
        return "TIMEOUT"

    return "RUNNING"
