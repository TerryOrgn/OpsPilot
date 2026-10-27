
import json
import logging

from webhook_notification_recovery_agent_observability import (
    WebhookNotificationRecoveryAgentObservability,
)


class FakeAgent:

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def run(self, message):
        self.calls += 1

        if self.error:
            raise self.error

        return self.result


class MemoryHandler(logging.Handler):

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def make_wrapper(agent, times, ids):
    handler = MemoryHandler()
    logger = logging.getLogger(
        f"test.agent.{id(handler)}"
    )
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    time_iter = iter(times)
    id_iter = iter(ids)

    wrapper = (
        WebhookNotificationRecoveryAgentObservability(
            agent=agent,
            logger=logger,
            clock=lambda: next(time_iter),
            request_id_factory=lambda: next(id_iter),
        )
    )

    return wrapper, handler


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


# 1. Successful tool call
agent = FakeAgent({
    "ok": True,
    "decision": "TOOL_CALL",
    "tool_name": "get_webhook_recovery_health",
    "tool_response": {
        "ok": True,
        "result": {
            "scheduler_health": "HEALTHY",
        },
    },
})

wrapper, handler = make_wrapper(
    agent,
    times=[10.0, 10.125],
    ids=["req-001"],
)

result = wrapper.run("检查健康")

check(
    "REQUEST_ID_ADDED",
    result["request_id"] == "req-001",
)

check(
    "DURATION_RECORDED",
    result["duration_ms"] == 125.0,
)

check(
    "ORIGINAL_RESULT_PRESERVED",
    result["ok"] is True
    and result["tool_response"]["result"][
        "scheduler_health"
    ] == "HEALTHY",
)

check(
    "SINGLE_LOG_EVENT",
    len(handler.records) == 1,
)

event = json.loads(handler.records[0])

check(
    "LOG_FIELDS_VALID",
    event["event"] == "AGENT_REQUEST_COMPLETED"
    and event["request_id"] == "req-001"
    and event["decision"] == "TOOL_CALL"
    and event["ok"] is True
    and event["duration_ms"] == 125.0,
)


# 2. Direct answer
agent = FakeAgent({
    "ok": True,
    "decision": "DIRECT_ANSWER",
    "tool_name": None,
    "tool_response": None,
    "answer": "你好",
})

wrapper, handler = make_wrapper(
    agent,
    times=[20.0, 20.010],
    ids=["req-002"],
)

result = wrapper.run("你好")
event = json.loads(handler.records[0])

check(
    "DIRECT_ANSWER_LOGGED",
    result["decision"] == "DIRECT_ANSWER"
    and event["tool_name"] is None
    and event["ok"] is True,
)


# 3. Tool failure
agent = FakeAgent({
    "ok": False,
    "decision": "TOOL_CALL",
    "tool_name": "unknown_tool",
    "tool_response": {
        "ok": False,
        "error": {
            "code": "UNKNOWN_TOOL",
            "message": "Tool is not registered",
        },
    },
})

wrapper, handler = make_wrapper(
    agent,
    times=[30.0, 30.050],
    ids=["req-003"],
)

result = wrapper.run("执行未知工具")
event = json.loads(handler.records[0])

check(
    "TOOL_ERROR_LOGGED",
    event["error_code"] == "UNKNOWN_TOOL"
    and event["ok"] is False,
)


# 4. Agent exception
agent = FakeAgent(
    error=RuntimeError("internal-secret")
)

wrapper, handler = make_wrapper(
    agent,
    times=[40.0, 40.020],
    ids=["req-004"],
)

result = wrapper.run("检查健康")
event = json.loads(handler.records[0])

check(
    "AGENT_EXCEPTION_HANDLED",
    result["ok"] is False
    and result["error"]["code"]
    == "AGENT_EXECUTION_FAILED",
)

check(
    "INTERNAL_SECRET_NOT_LOGGED",
    "internal-secret" not in handler.records[0],
)


# 5. Invalid Agent result
agent = FakeAgent(result=None)

wrapper, handler = make_wrapper(
    agent,
    times=[50.0, 50.005],
    ids=["req-005"],
)

result = wrapper.run("检查健康")

check(
    "INVALID_RESULT_HANDLED",
    result["ok"] is False
    and result["error"]["code"]
    == "INVALID_AGENT_RESULT",
)


# 6. Multiple requests have distinct IDs
agent = FakeAgent({
    "ok": True,
    "decision": "DIRECT_ANSWER",
    "answer": "OK",
})

wrapper, handler = make_wrapper(
    agent,
    times=[60.0, 60.010, 61.0, 61.020],
    ids=["req-006", "req-007"],
)

first = wrapper.run("请求一")
second = wrapper.run("请求二")

check(
    "REQUEST_IDS_DISTINCT",
    first["request_id"] != second["request_id"],
)

check(
    "MULTIPLE_LOG_EVENTS",
    len(handler.records) == 2,
)


# 7. Sensitive data excluded
all_logs = "\n".join(handler.records)

check(
    "USER_MESSAGES_NOT_LOGGED",
    "请求一" not in all_logs
    and "请求二" not in all_logs,
)


# 8. JSON compatibility
json.dumps(first)
json.dumps(second)

check(
    "RESULT_JSON_COMPATIBLE",
    True,
)


# 9. Dependency validation
try:
    WebhookNotificationRecoveryAgentObservability(
        agent=None
    )
except ValueError:
    rejected = True
else:
    rejected = False

check(
    "MISSING_AGENT_REJECTED",
    rejected,
)


print(
    "[TEST] ALL PASS: "
    "Recovery Agent observability"
)
