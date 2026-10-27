
from datetime import datetime

from apscheduler.schedulers.background import (
    BackgroundScheduler,
)

from webhook_notification_outbox_worker import (
    WebhookNotificationOutboxWorker,
)


class WebhookNotificationOutboxScheduler:

    def __init__(
        self,
        worker=None,
        interval_seconds=60,
    ):
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int)
            or interval_seconds <= 0
        ):
            raise ValueError(
                "interval_seconds must be a positive integer"
            )

        self.worker = (
            worker
            if worker is not None
            else WebhookNotificationOutboxWorker()
        )

        self.interval_seconds = interval_seconds

        self.scheduler = BackgroundScheduler()

        self.stats = {
            "total_runs": 0,
            "success_count": 0,
            "failure_count": 0,
            "last_run_time": None,
            "last_success_time": None,
            "last_error": None,
        }

    def _execute(self):
        self.stats["total_runs"] += 1
        self.stats["last_run_time"] = datetime.now()

        run_number = self.stats["total_runs"]

        print(
            f"[SCHEDULER] RUN_START={run_number}"
        )

        try:
            result = self.worker.run_once(limit=10)

            self.stats["success_count"] += 1
            self.stats["last_success_time"] = (
                datetime.now()
            )
            self.stats["last_error"] = None

            print(
                f"[SCHEDULER] RUN_SUCCESS={run_number} "
                f"stats={result}"
            )

        except Exception as error:
            self.stats["failure_count"] += 1
            self.stats["last_error"] = str(error)

            print(
                f"[SCHEDULER] RUN_FAILED={run_number} "
                f"error={error}"
            )

    def start(self):
        if self.scheduler.running:
            return

        self.scheduler.add_job(
            self._execute,
            trigger="interval",
            seconds=self.interval_seconds,
            id="webhook_outbox_worker",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

        self.scheduler.start()

        print(
            "[SCHEDULER] STARTED "
            f"interval={self.interval_seconds}s"
        )

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

        print("[SCHEDULER] STOPPED")
