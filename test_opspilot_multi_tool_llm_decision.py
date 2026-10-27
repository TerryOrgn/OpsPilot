
import json
from types import SimpleNamespace

from opspilot_multi_tool_llm_decision import (
    OpsPilotMultiToolLLMDecision,
)


def make_call(name, arguments):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=arguments,
    )


def make_response(output=None, output_text=""):
    return SimpleNamespace(
        output=output if output is not None else [],
        output_text=output_text,
    )


class FakeResponses:

    def __init__(self):
        self.response = make_response()
        self.last_request = None
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.last_request = kwargs
        return self.response


class FakeClient:

    def __init__(self):
        self.responses = FakeResponses()


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


def raises(expected_exception, action):
    try:
        action()
    except expected_exception:
        return True
    return False


client = FakeClient()
adapter = OpsPilotMultiToolLLMDecision(
    client=client,
    model="fake-model",
)


# 1. Two tool definitions
tools = adapter.get_tools()

check(
    "TWO_TOOLS_REGISTERED",
    len(tools) == 2,
)

names = {tool["name"] for tool in tools}

check(
    "WEBHOOK_TOOL_REGISTERED",
    "get_webhook_recovery_health" in names,
)

check(
    "JOB_TOOL_REGISTERED",
    "get_recent_abnormal_jobs" in names,
)

check(
    "STRICT_MODE_ENABLED",
    all(tool["strict"] is True for tool in tools),
)

check(
    "FUNCTION_TYPES",
    all(tool["type"] == "function" for tool in tools),
)

check(
    "TOOL_SCHEMAS_JSON_COMPATIBLE",
    isinstance(json.dumps(tools), str),
)


# 2. JOB function call
client.responses.response = make_response(
    output=[
        make_call(
            "get_recent_abnormal_jobs",
            '{"limit": 5}',
        )
    ]
)

job_decision = adapter.decide(
    "最近有失败的 JOB 吗？"
)

check(
    "JOB_TOOL_DECISION",
    job_decision["type"] == "TOOL_CALL",
)

check(
    "JOB_TOOL_NAME",
    job_decision["tool_name"]
    == "get_recent_abnormal_jobs",
)

check(
    "JOB_ARGUMENTS_PRESERVED",
    job_decision["arguments"] == '{"limit": 5}',
)


# 3. Webhook function call
client.responses.response = make_response(
    output=[
        make_call(
            "get_webhook_recovery_health",
            "{}",
        )
    ]
)

webhook_decision = adapter.decide(
    "Webhook Scheduler 健康吗？"
)

check(
    "WEBHOOK_TOOL_DECISION",
    webhook_decision["type"] == "TOOL_CALL",
)

check(
    "WEBHOOK_TOOL_NAME",
    webhook_decision["tool_name"]
    == "get_webhook_recovery_health",
)


# 4. Direct answer
client.responses.response = make_response(
    output=[],
    output_text="你好，我是 OpsPilot。",
)

direct = adapter.decide("你好")

check(
    "DIRECT_ANSWER_DECISION",
    direct["type"] == "DIRECT_ANSWER",
)

check(
    "DIRECT_ANSWER_CONTENT",
    direct["answer"] == "你好，我是 OpsPilot。",
)


# 5. Request configuration
request = client.responses.last_request

check(
    "PARALLEL_CALLS_DISABLED",
    request["parallel_tool_calls"] is False,
)

check(
    "TOOL_CHOICE_AUTO",
    request["tool_choice"] == "auto",
)

check(
    "MODEL_PASSED",
    request["model"] == "fake-model",
)

check(
    "TWO_TOOLS_SENT",
    len(request["tools"]) == 2,
)


# 6. Multiple calls rejected
client.responses.response = make_response(
    output=[
        make_call(
            "get_recent_abnormal_jobs",
            '{"limit": 5}',
        ),
        make_call(
            "get_webhook_recovery_health",
            "{}",
        ),
    ]
)

check(
    "MULTIPLE_CALLS_REJECTED",
    raises(
        ValueError,
        lambda: adapter.decide("查询所有状态"),
    ),
)


# 7. Empty answer rejected
client.responses.response = make_response(
    output=[],
    output_text="",
)

check(
    "EMPTY_ANSWER_REJECTED",
    raises(
        ValueError,
        lambda: adapter.decide("你好"),
    ),
)


# 8. Invalid input rejected
calls_before = client.responses.calls

check(
    "EMPTY_INPUT_REJECTED",
    raises(
        ValueError,
        lambda: adapter.decide("   "),
    ),
)

check(
    "EMPTY_INPUT_SKIPS_API",
    client.responses.calls == calls_before,
)


# 9. Invalid response structure
client.responses.response = make_response(
    output="invalid"
)

check(
    "INVALID_OUTPUT_REJECTED",
    raises(
        ValueError,
        lambda: adapter.decide("查询状态"),
    ),
)


# 10. Invalid function call
client.responses.response = make_response(
    output=[
        make_call(
            "get_recent_abnormal_jobs",
            {"limit": 5},
        )
    ]
)

check(
    "INVALID_ARGUMENT_TYPE_REJECTED",
    raises(
        ValueError,
        lambda: adapter.decide("查询 JOB"),
    ),
)


# 11. Dependency validation
check(
    "MISSING_CLIENT_REJECTED",
    raises(
        ValueError,
        lambda: OpsPilotMultiToolLLMDecision(
            client=None
        ),
    ),
)

check(
    "EMPTY_MODEL_REJECTED",
    raises(
        ValueError,
        lambda: OpsPilotMultiToolLLMDecision(
            client=client,
            model="",
        ),
    ),
)


print(
    "[TEST] ALL PASS: "
    "OpsPilot Multi Tool LLM Decision"
)
