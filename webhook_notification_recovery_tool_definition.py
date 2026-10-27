
from copy import deepcopy

from webhook_notification_recovery_health_tool import (
    WebhookNotificationRecoveryHealthTool,
)


class WebhookNotificationRecoveryToolDefinition:

    @staticmethod
    def get_definition():
        """
        Return the machine-readable tool definition.

        This tool accepts no arguments.
        It does not execute recovery.
        """

        definition = {
            "type": "function",
            "function": {
                "name": (
                    WebhookNotificationRecoveryHealthTool
                    .TOOL_NAME
                ),
                "description": (
                    WebhookNotificationRecoveryHealthTool
                    .TOOL_DESCRIPTION
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

        return deepcopy(definition)
