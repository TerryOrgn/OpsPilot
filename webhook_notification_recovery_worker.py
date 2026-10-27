
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


class WebhookNotificationRecoveryWorker:
    """
    批量恢复 Lease 已过期的 Outbox 任务。

    不负责发送通知。
    不负责定时调度。
    """

    def __init__(self, repository=None):
        self.repository = (
            repository
            if repository is not None
            else WebhookNotificationOutboxRepository()
        )

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        """
        执行一轮恢复扫描。

        返回：
            discovered
            recovered_retry
            recovered_dead
            skipped
            errors
        """

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        if (
            isinstance(retry_delay_seconds, bool)
            or not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        stats = {
            "discovered": 0,
            "recovered_retry": 0,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }

        tasks = (
            self.repository.get_expired_lease_notifications(
                limit=limit
            )
        )

        stats["discovered"] = len(tasks)

        for task in tasks:
            notification_id = task["ID"]
            claim_token = task["CLAIM_TOKEN"]

            if not claim_token:
                stats["skipped"] += 1
                print(
                    f"[RECOVERY] id={notification_id} "
                    "result=SKIPPED_NO_TOKEN"
                )
                continue

            try:
                result = (
                    self.repository.recover_expired_lease(
                        notification_id,
                        claim_token,
                        retry_delay_seconds=retry_delay_seconds,
                    )
                )

                event_type = result["event_type"]

                if event_type == "RECOVERED_RETRY":
                    stats["recovered_retry"] += 1

                elif event_type == "RECOVERED_DEAD":
                    stats["recovered_dead"] += 1

                elif event_type == "NOT_RECOVERED":
                    stats["skipped"] += 1

                else:
                    raise RuntimeError(
                        f"Unexpected recovery result: {event_type}"
                    )

                print(
                    f"[RECOVERY] id={notification_id} "
                    f"result={event_type}"
                )

            except Exception as error:
                stats["errors"] += 1

                print(
                    f"[RECOVERY] id={notification_id} "
                    f"result=ERROR "
                    f"error={type(error).__name__}: {error}"
                )

        return stats
