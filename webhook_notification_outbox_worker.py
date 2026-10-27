
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


class MockNotificationSender:
    """
    模拟通知发送器。

    event_id 包含 MOCK-FAIL 时模拟失败，
    其他情况模拟成功。
    """

    def send(self, notification):
        event_id = notification["EVENT_ID"]

        if "MOCK-FAIL" in event_id:
            raise RuntimeError(
                "Simulated notification delivery failure"
            )

        return True



class WebhookNotificationOutboxWorker:

    def __init__(self, repository=None, sender=None):
        self.repository = (
            repository
            if repository is not None
            else WebhookNotificationOutboxRepository()
        )

        self.sender = (
            sender
            if sender is not None
            else MockNotificationSender()
        )

    def run_once(self, limit=10):
        """
        执行一轮 Outbox 任务。

        使用 Claim Token 校验任务所有权。
        """

        tasks = self.repository.get_due_notifications(
            limit=limit
        )

        stats = {
            "discovered": len(tasks),
            "claimed": 0,
            "sent": 0,
            "retry": 0,
            "dead": 0,
            "skipped": 0,
            "ownership_rejected": 0,
        }

        for task in tasks:
            notification_id = task["ID"]

            # 1. 原子领取任务
            claim_result = (
                self.repository.claim_notification(
                    notification_id
                )
            )

            if claim_result["event_type"] != "CLAIMED":
                stats["skipped"] += 1
                continue

            stats["claimed"] += 1

            # 2. 保存本次领取的 Token
            claim_token = claim_result["claim_token"]

            if not claim_token:
                raise RuntimeError(
                    "Claim succeeded without claim_token"
                )

            # 3. 模拟发送
            try:
                self.sender.send(task)

            except Exception as error:
                # 4A. 发送失败：带 Token 更新
                failure_result = (
                    self.repository.mark_failed_with_token(
                        notification_id,
                        claim_token,
                        str(error) or type(error).__name__,
                    )
                )

                event_type = failure_result["event_type"]

                if event_type == "RETRY_SCHEDULED":
                    stats["retry"] += 1

                elif event_type == "MARKED_DEAD":
                    stats["dead"] += 1

                elif event_type == "NOT_UPDATED":
                    stats["ownership_rejected"] += 1

                else:
                    raise RuntimeError(
                        "Unexpected failure result: "
                        f"{failure_result}"
                    )

                print(
                    f"[WORKER] id={notification_id} "
                    f"result={event_type}"
                )

                continue

            # 4B. 发送成功：带 Token 更新
            sent_result = (
                self.repository.mark_sent_with_token(
                    notification_id,
                    claim_token,
                )
            )

            event_type = sent_result["event_type"]

            if event_type == "MARKED_SENT":
                stats["sent"] += 1

            elif event_type == "NOT_UPDATED":
                stats["ownership_rejected"] += 1

            else:
                raise RuntimeError(
                    "Unexpected sent result: "
                    f"{sent_result}"
                )

            print(
                f"[WORKER] id={notification_id} "
                f"result={event_type}"
            )

        return stats

