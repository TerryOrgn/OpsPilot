
from job_monitoring_tool_definition import (
    JobMonitoringToolDefinition,
)

from webhook_notification_recovery_tool_definition import (
    WebhookNotificationRecoveryToolDefinition,
)


class OpsPilotMultiToolLLMDecision:

    def __init__(self, client, model="gpt-4.1-mini"):
        if client is None:
            raise ValueError("client is required")

        if not isinstance(model, str) or not model.strip():
            raise ValueError("model is required")

        self._client = client
        self._model = model

    @staticmethod
    def get_tools():
        job_tool = (
            JobMonitoringToolDefinition.get_definition()
        )

        webhook_function = (
            WebhookNotificationRecoveryToolDefinition
            .get_definition()["function"]
        )

        webhook_tool = {
            "type": "function",
            "name": webhook_function["name"],
            "description": webhook_function["description"],
            "parameters": webhook_function["parameters"],
            "strict": True,
        }

        return [webhook_tool, job_tool]

    def decide(self, user_message):
        if (
            not isinstance(user_message, str)
            or not user_message.strip()
        ):
            raise ValueError("user_message is required")

        response = self._client.responses.create(
            model=self._model,
            instructions=(
                "You are OpsPilot, a read-only IT "
                "operations assistant. Use available "
                "tools for operational status questions. "
                "Never claim to modify, restart, or "
                "delete operational resources. "
                "Do not invent monitoring results."
            ),
            input=user_message,
            tools=self.get_tools(),
            tool_choice="auto",
            parallel_tool_calls=False,
            max_output_tokens=200,
        )

        output = response.output

        if not isinstance(output, list):
            raise ValueError("invalid response output")

        function_calls = [
            item for item in output
            if getattr(item, "type", None)
            == "function_call"
        ]

        if len(function_calls) > 1:
            raise ValueError(
                "multiple tool calls are not supported"
            )

        if len(function_calls) == 1:
            call = function_calls[0]

            if (
                not isinstance(call.name, str)
                or not isinstance(call.arguments, str)
            ):
                raise ValueError(
                    "invalid function call"
                )

            return {
                "type": "TOOL_CALL",
                "tool_name": call.name,
                "arguments": call.arguments,
            }

        answer = getattr(
            response, "output_text", None
        )

        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(
                "empty direct answer"
            )

        return {
            "type": "DIRECT_ANSWER",
            "answer": answer,
        }
