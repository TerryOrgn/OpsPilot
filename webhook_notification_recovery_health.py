
from datetime import datetime, timedelta


class WebhookNotificationRecoveryHealth:

    def __init__(
        self,
        failure_threshold=3,
        stale_seconds=300,
    ):
        if (
            type(failure_threshold) is not int
            or failure_threshold < 1
        ):
            raise ValueError(
                "failure_threshold must be positive"
            )

        if (
            type(stale_seconds) is not int
            or stale_seconds < 1
        ):
            raise ValueError(
                "stale_seconds must be positive"
            )

        self.failure_threshold = failure_threshold
        self.stale_seconds = stale_seconds

    def evaluate(self, stats, now=None):
        if now is None:
            now = datetime.now()

        consecutive_failures = stats.get(
            "consecutive_failures", 0
        )

        last_success_time = stats.get(
            "last_success_time"
        )

        if consecutive_failures >= self.failure_threshold:
            return {
                "status": "UNHEALTHY",
                "reason": "TOO_MANY_FAILURES",
            }

        if last_success_time is None:
            return {
                "status": "DEGRADED",
                "reason": "NO_SUCCESS_YET",
            }

        elapsed = (
            now - last_success_time
        ).total_seconds()

        if elapsed > self.stale_seconds:
            return {
                "status": "UNHEALTHY",
                "reason": "SUCCESS_TOO_OLD",
            }

        if consecutive_failures > 0:
            return {
                "status": "DEGRADED",
                "reason": "RECENT_FAILURES",
            }

        return {
            "status": "HEALTHY",
            "reason": "RUNNING_NORMALLY",
        }
    