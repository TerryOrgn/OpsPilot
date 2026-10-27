
from datetime import datetime
from threading import Lock

from apscheduler.schedulers.background import (
    BackgroundScheduler,
)

from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)

from webhook_notification_recovery_health import (
    WebhookNotificationRecoveryHealth,
)

class WebhookNotificationRecoveryScheduler:

    def __init__(
        self,
        worker=None,
        interval_seconds=60,
        limit=10,
        retry_delay_seconds=60,
    ):
        self.last_recovery_status = "NOT_RUN"
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or interval_seconds <= 0
        ):
            raise ValueError(
                "interval_seconds must be positive"
            )

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be between 1 and 100"
            )

        if (
            isinstance(retry_delay_seconds, bool)
            or not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        self.worker = (
            worker
            if worker is not None
            else WebhookNotificationRecoveryGuard()
        )

        if worker is None:
            self.worker = WebhookNotificationRecoveryGuard()

        elif isinstance(worker, WebhookNotificationRecoveryGuard):
            self.worker = worker

        else:
            raise TypeError(
                "Recovery Scheduler requires "
                "WebhookNotificationRecoveryGuard; "
                "direct Worker injection is forbidden"
            )

        self.interval_seconds = interval_seconds
        self.limit = limit
        self.retry_delay_seconds = retry_delay_seconds

        self.scheduler = BackgroundScheduler()

        self._lock = Lock()

        self.stats = {
            "total_runs": 0,
            "success_count": 0,
            "failure_count": 0,
            "consecutive_failures": 0,
            "skipped_overlaps": 0,
            "last_run_time": None,
            "last_success_time": None,
            "last_error_time": None,
            "last_error": None,
            "disabled_count": 0,
            "dry_run_count": 0,
            "executed_count": 0,
        }


    def run_once(self):
        """
        执行一轮 Recovery 调度。

        支持：
            DISABLED
            DRY_RUN
            EXECUTED
            SUCCESS（兼容旧 Worker）
            FAILED
            SKIPPED_OVERLAP
        """

        if not self._lock.acquire(blocking=False):
            self.stats["skipped_overlaps"] += 1

            print(
                "[RECOVERY-SCHEDULER] "
                "result=SKIPPED_OVERLAP"
            )

            return {
                "event_type": "SKIPPED_OVERLAP",
            }

        try:
            self.stats["total_runs"] += 1
            self.stats["last_run_time"] = datetime.now()

            result = self.worker.run_once(
                limit=self.limit,
                retry_delay_seconds=self.retry_delay_seconds,
            )

            event_type = result.get("event_type")

            # 兼容原有 Worker：没有 event_type，
            # 但有 errors 统计。
            if event_type is None:
                event_type = "SUCCESS"

            if event_type in ("DISABLED", "DRY_RUN", "EXECUTED"):
                self.last_recovery_status = event_type

            allowed_events = {
                "DISABLED",
                "DRY_RUN",
                "EXECUTED",
                "SUCCESS",
            }

            if event_type not in allowed_events:
                raise RuntimeError(
                    f"Unexpected scheduler result: {event_type}"
                )

            if result.get("errors", 0) > 0:
                raise RuntimeError(
                    "Recovery worker reported "
                    f"{result['errors']} task errors"
                )

            self.stats["success_count"] += 1
            self.stats["consecutive_failures"] = 0
            self.stats["last_success_time"] = datetime.now()
            self.stats["last_error"] = None

            if event_type == "DISABLED":
                self.stats["disabled_count"] += 1

            elif event_type == "DRY_RUN":
                self.stats["dry_run_count"] += 1

            elif event_type == "EXECUTED":
                self.stats["executed_count"] += 1

            print(
                "[RECOVERY-SCHEDULER] "
                f"result={event_type} stats={result}"
            )

            return {
                "event_type": event_type,
                "worker_stats": result,
            }

        except Exception as error:
            self.last_recovery_status = "FAILED"
            self.stats["failure_count"] += 1
            self.stats["consecutive_failures"] += 1
            self.stats["last_error_time"] = datetime.now()
            self.stats["last_error"] = (
                f"{type(error).__name__}: {error}"
            )

            print(
                "[RECOVERY-SCHEDULER] "
                f"result=FAILED "
                f"error={self.stats['last_error']}"
            )

            return {
                "event_type": "FAILED",
                "error": self.stats["last_error"],
            }

        finally:
            self._lock.release()


    def start(self):
        if self.scheduler.running:
            return

        if self.scheduler.get_job("recovery_scan") is None:
            self.scheduler.add_job(
                self.run_once,
                trigger="interval",
                seconds=self.interval_seconds,
                id="recovery_scan",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )

        self.scheduler.start()

        print(
            "[RECOVERY-SCHEDULER] "
            f"STARTED interval={self.interval_seconds}s"
        )

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)

        print("[RECOVERY-SCHEDULER] STOPPED")

    def get_stats(self):
        return dict(self.stats)

    def get_health(self, now=None):
        """
        Read-only scheduler health evaluation.

        Does not trigger Worker or database operations.
        """
        evaluator = WebhookNotificationRecoveryHealth(
            failure_threshold=3,
            stale_seconds=300,
        )

        stats = self.get_stats()

        result = evaluator.evaluate(
            stats,
            now=now,
        )

        return {
            "status": result["status"],
            "reason": result["reason"],
            "total_runs": stats["total_runs"],
            "consecutive_failures": stats[
                "consecutive_failures"
            ],
            "last_success_time": stats[
                "last_success_time"
            ],
            "recovery_status": self.last_recovery_status,
        }

    def get_health_snapshot(self, now=None):
        """
        Return a read-only Recovery health snapshot.

        No Worker execution and no database access.
        """
        health = self.get_health(now=now)

        guard = self.worker

        if not guard.enabled:
            ready = False
            readiness_reason = "GUARD_DISABLED"
        elif guard.dry_run:
            ready = False
            readiness_reason = "DRY_RUN_ENABLED"
        elif health["status"] == "UNHEALTHY":
            ready = False
            readiness_reason = "SCHEDULER_UNHEALTHY"
        else:
            ready = True
            readiness_reason = "READY"

        return {
            "scheduler_health": health["status"],
            "health_reason": health["reason"],
            "recovery_status": health["recovery_status"],
            "ready_for_recovery": ready,
            "readiness_reason": readiness_reason,
            "total_runs": health["total_runs"],
            "consecutive_failures": health[
                "consecutive_failures"
            ],
            "last_success_time": health[
                "last_success_time"
            ],
        }
