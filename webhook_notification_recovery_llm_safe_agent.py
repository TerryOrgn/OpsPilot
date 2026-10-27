
from webhook_notification_recovery_tool_dispatcher import (
    WebhookNotificationRecoveryToolDispatcher,
)


class WebhookNotificationRecoveryLLMSafeAgent:

    def __init__(self, scheduler, llm):
        if scheduler is None:
            raise ValueError("scheduler is required")

        if llm is None:
            raise ValueError("llm is required")

        self._llm = llm
        self._dispatcher = (
            WebhookNotificationRecoveryToolDispatcher(
                scheduler=scheduler
            )
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

    def run(self, user_message):
        if (
            not isinstance(user_message, str)
            or not user_message.strip()
        ):
            return self._error(
                "INVALID_USER_MESSAGE",
                "User message must be non-empty",
            )

        try:
            decision = self._llm.decide(user_message)
        except Exception:
            return self._error(
                "LLM_DECISION_FAILED",
                "LLM decision failed",
            )

        if not isinstance(decision, dict):
            return self._error(
                "INVALID_DECISION",
                "LLM decision must be an object",
            )

        decision_type = decision.get("decision")

        if decision_type == "DIRECT_ANSWER":
            answer = decision.get("answer")

            if not isinstance(answer, str):
                return self._error(
                    "INVALID_DECISION",
                    "Direct answer must be a string",
                )

            return {
                "ok": True,
                "decision": "DIRECT_ANSWER",
                "tool_name": None,
                "tool_response": None,
                "answer": answer,
            }

        if decision_type != "TOOL_CALL":
            return self._error(
                "INVALID_DECISION",
                "Unsupported LLM decision",
            )

        tool_name = decision.get("name")
        arguments = decision.get("arguments")

        # Dispatcher is the authorization boundary.
        tool_response = self._dispatcher.dispatch(
            tool_name,
            arguments,
        )

        return {
            "ok": tool_response["ok"],
            "decision": "TOOL_CALL",
            "tool_name": tool_name,
            "tool_response": tool_response,
        }
