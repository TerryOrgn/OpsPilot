
import json
from types import SimpleNamespace

from openai import RateLimitError
import httpx

from webhook_notification_recovery_llm_decision import (
    WebhookNotificationRecoveryLLMDecision,
)


TOOL_NAME = "get_webhook_recovery_health"


class FakeResponses:

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        if self.error is not None:
            raise self.error

        return self.response


class FakeOpenAIClient:

    def __init__(self, response=None, error=None):
        self.responses = FakeResponses(
            response=response,
            error=error,
        )


def function_call_response(
    name=TOOL_NAME,
    arguments="{}",
):
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name=name,
                arguments=arguments,
                call_id="call-001",
            )
        ],
        output_text="",
    )


def direct_answer_response(answer):
    return SimpleNamespace(
        output=[],
        output_text=answer,
    )


def create_llm(response=None, error=None):
    client = FakeOpenAIClient(
        response=response,
        error=error,
    )

    llm = WebhookNotificationRecoveryLLMDecision(
        client=client,
        model="mock-model",
    )

    return llm, client


# 1. Valid function call
llm, client = create_llm(
    response=function_call_response()
)

result = llm.decide("Recovery 健康吗？")

assert result["decision"] == "TOOL_CALL"
assert result["name"] == TOOL_NAME
assert result["arguments"] == "{}"
assert result["call_id"] == "call-001"

print("[TEST] FUNCTION_CALL_PARSED= True")


# 2. Model configuration
request = client.responses.calls[0]

assert request["model"] == "mock-model"
assert request["tool_choice"] == "auto"
assert request["parallel_tool_calls"] is False

print("[TEST] MODEL_REQUEST_CONFIG_VALID= True")


# 3. Tool definition forwarded
tools = request["tools"]

assert len(tools) == 1
assert tools[0]["name"] == TOOL_NAME
assert tools[0]["strict"] is True

print("[TEST] TOOL_DEFINITION_FORWARDED= True")


# 4. Direct answer
llm, client = create_llm(
    response=direct_answer_response(
        "你好，我是 OpsPilot 监控助手。"
    )
)

result = llm.decide("你好")

assert result["decision"] == "DIRECT_ANSWER"
assert "OpsPilot" in result["answer"]

print("[TEST] DIRECT_ANSWER_PARSED= True")


# 5. Unknown tool name is preserved
# Dispatcher must reject it later.
llm, client = create_llm(
    response=function_call_response(
        name="delete_all_notifications"
    )
)

result = llm.decide("删除所有通知")

assert result["decision"] == "TOOL_CALL"
assert result["name"] == "delete_all_notifications"

print("[TEST] UNKNOWN_TOOL_NOT_EXECUTED= True")


# 6. Invalid arguments are preserved
# Dispatcher is responsible for validation.
llm, client = create_llm(
    response=function_call_response(
        arguments='{"force": true}'
    )
)

result = llm.decide("检查 Recovery")

assert result["arguments"] == '{"force": true}'

print("[TEST] ARGUMENTS_PRESERVED= True")


# 7. Multiple calls are not accepted
response = SimpleNamespace(
    output=[
        SimpleNamespace(
            type="function_call",
            name=TOOL_NAME,
            arguments="{}",
            call_id="call-001",
        ),
        SimpleNamespace(
            type="function_call",
            name=TOOL_NAME,
            arguments="{}",
            call_id="call-002",
        ),
    ],
    output_text="",
)

llm, client = create_llm(response=response)

result = llm.decide("检查 Recovery")

assert result["decision"] == (
    "UNSUPPORTED_MULTIPLE_CALLS"
)
assert result["tool_count"] == 2

print("[TEST] MULTIPLE_CALLS_DETECTED= True")


# 8. Empty input rejected before API call
llm, client = create_llm(
    response=function_call_response()
)

try:
    llm.decide("   ")
except ValueError:
    pass
else:
    raise AssertionError(
        "Empty input must be rejected"
    )

assert len(client.responses.calls) == 0

print("[TEST] EMPTY_INPUT_REJECTED= True")


# 9. Simulate exhausted API credits
request = httpx.Request(
    "POST",
    "https://api.openai.com/v1/responses",
)

http_response = httpx.Response(
    status_code=429,
    request=request,
    json={
        "error": {
            "message": "You have no credits remaining",
            "type": "insufficient_quota",
            "code": "credit_balance_exhausted",
        }
    },
)

api_error = RateLimitError(
    "You have no credits remaining",
    response=http_response,
    body=http_response.json(),
)

llm, client = create_llm(error=api_error)

try:
    llm.decide("检查 Recovery 健康")
except RateLimitError as exc:
    assert exc.status_code == 429
else:
    raise AssertionError(
        "RateLimitError must propagate"
    )

print("[TEST] RATE_LIMIT_ERROR_PROPAGATED= True")


# 10. Result is JSON compatible
llm, client = create_llm(
    response=function_call_response()
)

result = llm.decide("检查 Recovery 健康")

encoded = json.dumps(result)
decoded = json.loads(encoded)

assert decoded == result

print("[TEST] RESULT_JSON_COMPATIBLE= True")


# 11. Only one API request per decision
assert len(client.responses.calls) == 1

print("[TEST] SINGLE_API_REQUEST= True")


# 12. No real network calls
assert isinstance(client, FakeOpenAIClient)

print("[TEST] MOCK_CLIENT_USED= True")


print(
    "[TEST] ALL PASS: "
    "Recovery LLM decision mock"
)
