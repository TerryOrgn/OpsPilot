
import json

from webhook_notification_recovery_health_serializer import (
    WebhookNotificationRecoveryHealthSerializer,
)


class WebhookNotificationRecoveryHealthTool:

    TOOL_NAME = "get_webhook_recovery_health"

    TOOL_DESCRIPTION = (
        "Read the current health status of the "
        "Webhook Notification Recovery Scheduler. "
        "This tool is read-only and does not "
        "execute recovery operations."
    )

    def __init__(self, scheduler):
        if scheduler is None:
            raise ValueError("scheduler is required")

        self._scheduler = scheduler
        self._serializer = (
            WebhookNotificationRecoveryHealthSerializer()
        )

    def execute(self):
        snapshot = self._scheduler.get_health_snapshot()

        result = self._serializer.serialize(
            snapshot,
            schema_version="1.0",
        )

        # 确认结果能够真正转换成 JSON
        json.dumps(result)

        return result


def get_recovery_health_tool(scheduler):
    """
    Read-only Agent tool entry point.

    Returns a JSON-compatible dictionary.
    Does not call scheduler.run_once().
    """
    tool = WebhookNotificationRecoveryHealthTool(
        scheduler=scheduler
    )

    return tool.execute()
