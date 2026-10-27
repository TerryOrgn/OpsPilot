
from threading import Lock

from webhook_metrics_alert_pipeline import (
    WebhookMetricsAlertPipeline,
)
from webhook_alert_repository import WebhookAlertRepository

from webhook_alert_notification_policy import (
    WebhookAlertNotificationPolicy,
)

class WebhookMetricsAlertService:

    def __init__(
        self,
        metrics=None,
        repository=None,
        alert_key="WEBHOOK_ERROR_RATE:default",
        min_requests=10,
        error_threshold=20.0,
    ):
        self._pipeline = WebhookMetricsAlertPipeline(
            metrics=metrics,
            min_requests=min_requests,
            error_threshold=error_threshold,
        )

        self._repository = (
            repository
            if repository is not None
            else WebhookAlertRepository()
        )

        self._alert_key = alert_key
        self._lock = Lock()

        # 当前进程中尚未成功持久化的操作
        self._pending_operation = None
        self._notification_policy = WebhookAlertNotificationPolicy()

    def _execute_operation(self, operation):
        if operation["type"] == "ALERT":
            return self._repository.create_or_update_alert(
                alert_key=self._alert_key,
                alert_type="WEBHOOK_ERROR_RATE",
                alert_level="WARNING",
                alert_message=operation["message"],
            )

        if operation["type"] == "RESOLVE":
            changed = self._repository.resolve_alert(
                alert_key=self._alert_key,
                reason=operation["reason"],
            )

            return {
                "alert_id": None,
                "event_type": (
                    "RESOLVED" if changed else "NO_CHANGE"
                ),
            }

        raise ValueError(
            f"Unsupported operation: {operation['type']}"
        )

    def _persist(self, operation):
        # 先登记 Pending，再尝试写入。
        self._pending_operation = operation

        saved = self._execute_operation(operation)

        # 只有 Repository 正常返回才清除 Pending。
        self._pending_operation = None

        return saved

    def run(self):
        with self._lock:

            retry_event = "NO_CHANGE"

            # 1. 优先重试上次失败的数据库操作
            if self._pending_operation is not None:
                saved = self._execute_operation(
                    self._pending_operation
                )

                retry_event = saved["event_type"]

                self._pending_operation = None

            # 2. 补偿完成后，才执行新一轮采样
            result = self._pipeline.run()
            status = result["monitor_status"]

            db_event = "NO_CHANGE"
            alert_id = None

            if status == "ALERT":
                window = result["window"]
                error_rate = window["window_error_rate"]

                operation = {
                    "type": "ALERT",
                    "message": (
                        f"Webhook error rate: {error_rate}%"
                    ),
                }

                saved = self._persist(operation)

                db_event = saved["event_type"]
                alert_id = saved["alert_id"]

            elif status == "OK":
                operation = {
                    "type": "RESOLVE",
                    "reason": (
                        "Webhook error rate returned to normal"
                    ),
                }

                saved = self._persist(operation)

                db_event = saved["event_type"]

            notification = self._notification_policy.decide(
                db_event=db_event,
                retry_event=retry_event,
            )

            return {
                "monitor_status": status,
                "pipeline_event": result["event"],
                "db_event": db_event,
                "retry_event": retry_event,
                "alert_id": alert_id,
                "window": result["window"],
                "has_pending": (
                        self._pending_operation is not None
                ),
                "notification_action": notification["action"],
                "notification_reason": notification["reason"],
                "notification_events": notification["events"],
            }

