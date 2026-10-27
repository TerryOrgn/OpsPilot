
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)
from webhook_notification_recovery_worker import (
    WebhookNotificationRecoveryWorker,
)


class WebhookNotificationRecoveryGuard:
    """
    Recovery 安全执行入口。

    默认禁用实际恢复。
    默认 DRY_RUN。
    限制每轮批次大小。
    """

    def __init__(
        self,
        repository=None,
        worker=None,
        enabled=False,
        dry_run=True,
        max_batch_size=10,
        retry_delay_seconds=60,
    ):
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")

        if type(dry_run) is not bool:
            raise ValueError("dry_run must be bool")

        if (
            type(max_batch_size) is not int
            or not 1 <= max_batch_size <= 100
        ):
            raise ValueError(
                "max_batch_size must be between 1 and 100"
            )

        if (
            type(retry_delay_seconds) is not int
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        self.repository = (
            repository
            if repository is not None
            else WebhookNotificationOutboxRepository()
        )

        self.worker = (
            worker
            if worker is not None
            else WebhookNotificationRecoveryWorker(
                repository=self.repository
            )
        )

        self.enabled = enabled
        self.dry_run = dry_run
        self.max_batch_size = max_batch_size
        self.retry_delay_seconds = retry_delay_seconds

    def run_once(
            self,
            limit=None,
            retry_delay_seconds=None,
    ):
        if limit is not None:
            if type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError("Invalid recovery limit")

            if limit != self.max_batch_size:
                raise ValueError(
                    "Guard batch limit mismatch: "
                    f"scheduler={limit}, "
                    f"guard={self.max_batch_size}"
                )

        if retry_delay_seconds is not None:
            if (
                type(retry_delay_seconds) is not int
                or retry_delay_seconds < 0
            ):
                raise ValueError("Invalid retry delay")

            if retry_delay_seconds != self.retry_delay_seconds:
                raise ValueError(
                    "Guard retry delay mismatch: "
                    f"scheduler={retry_delay_seconds}, "
                    f"guard={self.retry_delay_seconds}"
                )
        # 未启用时直接返回，不访问数据库。
        if not self.enabled:
            print(
                "[RECOVERY-GUARD] result=DISABLED"
            )

            return {
                "event_type": "DISABLED",
                "discovered": 0,
                "recovered_retry": 0,
                "recovered_dead": 0,
                "skipped": 0,
                "errors": 0,
            }

        if self.dry_run:
            tasks = (
                self.repository.get_expired_lease_notifications(
                    limit=self.max_batch_size
                )
            )

            missing_token = sum(
                1
                for task in tasks
                if not task.get("CLAIM_TOKEN")
            )

            print(
                "[RECOVERY-GUARD] "
                f"result=DRY_RUN "
                f"candidates={len(tasks)} "
                f"missing_token={missing_token}"
            )

            return {
                "event_type": "DRY_RUN",
                "discovered": len(tasks),
                "missing_token": missing_token,
                "recovered_retry": 0,
                "recovered_dead": 0,
                "skipped": 0,
                "errors": 0,
            }

        stats = self.worker.run_once(
            limit=self.max_batch_size,
            retry_delay_seconds=self.retry_delay_seconds,
        )

        print(
            "[RECOVERY-GUARD] "
            f"result=EXECUTED stats={stats}"
        )

        return {
            "event_type": "EXECUTED",
            **stats,
        }
