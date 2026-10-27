
import json

from webhook_notification_recovery_health_tool import (
    WebhookNotificationRecoveryHealthTool,
)


class WebhookNotificationRecoveryToolDispatcher:

    def __init__(self, scheduler):
        if scheduler is None:
            raise ValueError("scheduler is required")

        self._health_tool = (
            WebhookNotificationRecoveryHealthTool(
                scheduler=scheduler
            )
        )

        self._allowed_tools = {
            self._health_tool.TOOL_NAME:
                self._health_tool.execute
        }

    def dispatch(self, tool_name, arguments_json):
        """
        Dispatch a validated tool call.

        Only the read-only health tool is allowed.
        """

        # 1. Validate tool name
        if (
            not isinstance(tool_name, str)
            or tool_name not in self._allowed_tools
        ):
            return self._error(
                "UNKNOWN_TOOL",
                "Tool is not registered",
            )

        # 2. Require JSON text
        if not isinstance(arguments_json, str):
            return self._error(
                "INVALID_ARGUMENTS",
                "Arguments must be a JSON string",
            )

        # 3. Parse JSON
        try:
            arguments = json.loads(arguments_json)
        except (json.JSONDecodeError, ValueError):
            return self._error(
                "INVALID_JSON",
                "Arguments are not valid JSON",
            )

        # 4. Only an empty JSON object is accepted
        if not isinstance(arguments, dict):
            return self._error(
                "INVALID_ARGUMENTS",
                "Arguments must be a JSON object",
            )

        if arguments:
            return self._error(
                "UNEXPECTED_ARGUMENTS",
                "This tool accepts no arguments",
            )

        # 5. Execute allowlisted tool
        try:
            result = self._allowed_tools[tool_name]()

            return {
                "ok": True,
                "tool_name": tool_name,
                "result": result,
            }

        except Exception:
            # Do not expose exception internals
            return self._error(
                "TOOL_EXECUTION_FAILED",
                "Tool execution failed",
            )

    @staticmethod
    def _error(code, message):
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
    