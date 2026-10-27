
import os

from openai import OpenAI

from webhook_notification_recovery_tool_definition import (
    WebhookNotificationRecoveryToolDefinition,
)


class WebhookNotificationRecoveryLLMDecision:

    def __init__(self, client=None, model=None):
        self._client = client or OpenAI(timeout=20.0)
        self._model = model or os.getenv(
            "OPSPILOT_LLM_MODEL",
            "gpt-4.1-mini",
        )

    @staticmethod
    def get_tools():
        # Convert existing Chat Completions tool definition
        # to Responses API tool definition.
        definition = (
            WebhookNotificationRecoveryToolDefinition
            .get_definition()["function"]
        )

        return [{
            "type": "function",
            "name": definition["name"],
            "description": definition["description"],
            "parameters": definition["parameters"],
            "strict": True,
        }]

    def decide(self, user_message):
        if (
            not isinstance(user_message, str)
            or not user_message.strip()
        ):
            raise ValueError("user_message must be non-empty")

        response = self._client.responses.create(
            model=self._model,
            instructions=(
                "You are an OpsPilot read-only monitoring assistant. "
                "Use the provided tool only when the user asks "
                "about Webhook Recovery scheduler health or status. "
                "For greetings and unrelated questions, do not "
                "call tools. Never claim to have executed recovery "
                "or retrieved live status without tool results. "
                "You cannot delete or modify notifications."
            ),
            input=user_message,
            tools=self.get_tools(),
            tool_choice="auto",
            parallel_tool_calls=False,
            max_output_tokens=200,
        )

        calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        # This learning exercise supports at most one call.
        if len(calls) > 1:
            return {
                "decision": "UNSUPPORTED_MULTIPLE_CALLS",
                "tool_count": len(calls),
            }

        if len(calls) == 1:
            call = calls[0]

            return {
                "decision": "TOOL_CALL",
                "name": call.name,
                "arguments": call.arguments,
                "call_id": call.call_id,
            }

        return {
            "decision": "DIRECT_ANSWER",
            "answer": response.output_text or "",
        }
