
import json
import logging
import time
import uuid
from webhook_notification_recovery_trace_context import (
    set_request_id,
    reset_request_id,
)

class WebhookNotificationRecoveryAgentObservability:

    def __init__(
        self,
        agent,
        logger=None,
        clock=None,
        request_id_factory=None,
    ):
        if agent is None:
            raise ValueError("agent is required")

        self._agent = agent
        self._logger = logger or logging.getLogger(
            "opspilot.agent"
        )
        self._clock = clock or time.perf_counter
        self._request_id_factory = (
            request_id_factory or
            (lambda: uuid.uuid4().hex)
        )

    def run(self, user_message):
        request_id = self._request_id_factory()
        token = set_request_id(request_id)

        try:
            start = self._clock()

            try:
                result = self._agent.run(user_message)

                if not isinstance(result, dict):
                    result = {
                        "ok": False,
                        "error": {
                            "code": "INVALID_AGENT_RESULT",
                            "message": "Agent result must be an object",
                        },
                    }

            except Exception:
                result = {
                    "ok": False,
                    "error": {
                        "code": "AGENT_EXECUTION_FAILED",
                        "message": "Agent execution failed",
                    },
                }

            duration_ms = max(
                0,
                round((self._clock() - start) * 1000, 3),
            )

            decision = result.get("decision")
            tool_name = result.get("tool_name")

            error = result.get("error")

            if not error:
                tool_response = result.get("tool_response")

                if isinstance(tool_response, dict):
                    error = tool_response.get("error")

            error_code = None

            if isinstance(error, dict):
                code = error.get("code")

                if isinstance(code, str):
                    error_code = code

            event = {
                "event": "AGENT_REQUEST_COMPLETED",
                "request_id": request_id,
                "ok": result.get("ok") is True,
                "decision": decision,
                "tool_name": tool_name,
                "error_code": error_code,
                "duration_ms": duration_ms,
            }

            self._logger.info(
                json.dumps(
                    event,
                    ensure_ascii=False,
                )
            )

            return {
                **result,
                "request_id": request_id,
                "duration_ms": duration_ms,
            }

        finally:
            reset_request_id(token)

        try:
            result = self._agent.run(user_message)

            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "error": {
                        "code": "INVALID_AGENT_RESULT",
                        "message": "Agent result must be an object",
                    },
                }

        except Exception:
            result = {
                "ok": False,
                "error": {
                    "code": "AGENT_EXECUTION_FAILED",
                    "message": "Agent execution failed",
                },
            }

        duration_ms = max(
            0,
            round((self._clock() - start) * 1000, 3),
        )

        decision = result.get("decision")
        tool_name = result.get("tool_name")

        error = result.get("error")

        if not error:
            tool_response = result.get("tool_response")
            if isinstance(tool_response, dict):
                error = tool_response.get("error")

        error_code = None

        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, str):
                error_code = code

        event = {
            "event": "AGENT_REQUEST_COMPLETED",
            "request_id": request_id,
            "ok": result.get("ok") is True,
            "decision": decision,
            "tool_name": tool_name,
            "error_code": error_code,
            "duration_ms": duration_ms,
        }

        # Do not log user messages, API keys,
        # tool arguments, or raw tool results.
        self._logger.info(
            json.dumps(
                event,
                ensure_ascii=False,
            )
        )

        return {
            **result,
            "request_id": request_id,
            "duration_ms": duration_ms,
        }
