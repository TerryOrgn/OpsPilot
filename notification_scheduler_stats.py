
from datetime import datetime


class NotificationSchedulerStats:

    def __init__(self):
        self.total_runs = 0
        self.success_count = 0
        self.failure_count = 0
        self.consecutive_failures = 0

        self.last_run_time = None
        self.last_success_time = None
        self.last_error_time = None

    def record_result(self, cycle_status):
        now = datetime.now().astimezone()

        self.total_runs += 1
        self.last_run_time = now

        if cycle_status == "SUCCESS":
            self.success_count += 1
            self.consecutive_failures = 0
            self.last_success_time = now

        elif cycle_status == "FAILED":
            self.failure_count += 1
            self.consecutive_failures += 1
            self.last_error_time = now

        else:
            raise ValueError(
                f"Unsupported cycle status: {cycle_status}"
            )

    def snapshot(self):
        return {
            "total_runs": self.total_runs,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "last_run_time": self.last_run_time,
            "last_success_time": self.last_success_time,
            "last_error_time": self.last_error_time
        }


    def get_health_status(self, failure_threshold=3):
        """
        根据连续失败次数判断通知调度器健康状态。
        """
        if failure_threshold < 1:
            raise ValueError(
                "failure_threshold must be >= 1"
            )

        if self.consecutive_failures >= failure_threshold:
            return "UNHEALTHY"

        return "HEALTHY"


    def detect_health_transition(self, previous_health, failure_threshold=3):
        """
        比较前后健康状态，仅在状态发生变化时返回事件。
        """
        current_health = self.get_health_status(failure_threshold)

        if previous_health == current_health:
            return None

        if previous_health == "HEALTHY" and current_health == "UNHEALTHY":
            return "HEALTH_DEGRADED"

        if previous_health == "UNHEALTHY" and current_health == "HEALTHY":
            return "HEALTH_RECOVERED"

        return None
