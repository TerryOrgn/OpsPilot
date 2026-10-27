
import json

from job_monitoring_tool import JobMonitoringTool

from webhook_notification_recovery_health_tool import (
    WebhookNotificationRecoveryHealthTool,
)


class OpsPilotMultiToolDispatcher:


    def __init__(
            self,
            scheduler,
            job_repository,
            enable_job_timeout_detection=False,
            now_provider=None,
    ):
        if scheduler is None:
            raise ValueError("scheduler is required")

        if job_repository is None:
            raise ValueError("job_repository is required")

        self._health_tool = (
            WebhookNotificationRecoveryHealthTool(
                scheduler=scheduler
            )
        )


        self._job_tool = JobMonitoringTool(
            repository=job_repository,
            enable_timeout_detection=enable_job_timeout_detection,
            now_provider=now_provider,
        )

        self._allowed_tools = {
            self._health_tool.TOOL_NAME:
                self._execute_health,
            self._job_tool.TOOL_NAME:
                self._execute_jobs,
        }

    @staticmethod
    def _error(code, message):
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }

    def _execute_health(self, arguments):
        if arguments:
            return self._error(
                "UNEXPECTED_ARGUMENTS",
                "This tool accepts no arguments",
            )

        result = self._health_tool.execute()

        return {
            "ok": True,
            "tool_name": self._health_tool.TOOL_NAME,
            "result": result,
        }

    def _execute_jobs(self, arguments):
        if set(arguments) != {"limit"}:
            return self._error(
                "INVALID_ARGUMENTS",
                "JOB tool requires only limit",
            )

        limit = arguments["limit"]

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            return self._error(
                "INVALID_ARGUMENTS",
                "limit must be an integer from 1 to 100",
            )

        result = self._job_tool.execute(
            limit=limit
        )

        return {
            "ok": True,
            "tool_name": self._job_tool.TOOL_NAME,
            "result": result,
        }

    def dispatch(self, tool_name, arguments_json):
        if (
            not isinstance(tool_name, str)
            or tool_name not in self._allowed_tools
        ):
            return self._error(
                "UNKNOWN_TOOL",
                "Tool is not registered",
            )

        if not isinstance(arguments_json, str):
            return self._error(
                "INVALID_ARGUMENTS",
                "Arguments must be a JSON string",
            )

        try:
            arguments = json.loads(arguments_json)
        except (json.JSONDecodeError, ValueError):
            return self._error(
                "INVALID_JSON",
                "Arguments are not valid JSON",
            )

        if not isinstance(arguments, dict):
            return self._error(
                "INVALID_ARGUMENTS",
                "Arguments must be a JSON object",
            )

        try:
            return self._allowed_tools[tool_name](
                arguments
            )
        except Exception:
            return self._error(
                "TOOL_EXECUTION_FAILED",
                "Tool execution failed",
            )
