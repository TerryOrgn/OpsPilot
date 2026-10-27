
import json

from webhook_notification_recovery_llm_safe_agent import (
    WebhookNotificationRecoveryLLMSafeAgent,
)


TOOL_NAME = "get_webhook_recovery_health"


class FakeScheduler:

    def __init__(self):
        self.health_calls = 0
        self.recovery_calls = 0
        self.fail_health = False

    def get_health_snapshot(self):
        self.health_calls += 1

        if self.fail_health:
            raise RuntimeError("database-secret")

        return {
            "scheduler_health": "HEALTHY",
            "health_reason": "OK",
            "recovery_status": "NOT_RUN",
            "ready_for_recovery": True,
            "readiness_reason": "READY",
            "total_runs": 0,
            "consecutive_failures": 0,
            "last_success_time": None,
        }

    def run_once(self):
        self.recovery_calls += 1
        raise AssertionError("Recovery must not run")


class FakeLLM:

    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def decide(self, message):
        self.calls += 1
        return self.decision


def make_agent(decision):
    scheduler = FakeScheduler()
    llm = FakeLLM(decision)

    agent = WebhookNotificationRecoveryLLMSafeAgent(
        scheduler=scheduler,
        llm=llm,
    )

    return agent, scheduler, llm


def tool_call(name=TOOL_NAME, arguments="{}"):
    return {
        "decision": "TOOL_CALL",
        "name": name,
        "arguments": arguments,
    }


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


# 1. Tool name is a list
agent, scheduler, llm = make_agent(
    tool_call(name=[TOOL_NAME])
)
result = agent.run("检查状态")

check(
    "LIST_TOOL_NAME_REJECTED",
    result["ok"] is False
    and result["tool_response"]["error"]["code"]
    == "UNKNOWN_TOOL",
)


# 2. Tool name is an integer
agent, scheduler, llm = make_agent(
    tool_call(name=123)
)
result = agent.run("检查状态")

check(
    "INTEGER_TOOL_NAME_REJECTED",
    result["ok"] is False
    and result["tool_response"]["error"]["code"]
    == "UNKNOWN_TOOL",
)


# 3. Arguments are a dictionary instead of JSON
agent, scheduler, llm = make_agent(
    tool_call(arguments={})
)
result = agent.run("检查状态")

check(
    "DICT_ARGUMENTS_REJECTED",
    result["ok"] is False
    and result["tool_response"]["error"]["code"]
    == "INVALID_ARGUMENTS",
)


# 4. Missing arguments
agent, scheduler, llm = make_agent({
    "decision": "TOOL_CALL",
    "name": TOOL_NAME,
})
result = agent.run("检查状态")

check(
    "MISSING_ARGUMENTS_REJECTED",
    result["ok"] is False
    and result["tool_response"]["error"]["code"]
    == "INVALID_ARGUMENTS",
)


# 5. Empty direct answer is currently accepted
agent, scheduler, llm = make_agent({
    "decision": "DIRECT_ANSWER",
    "answer": "",
})
result = agent.run("你好")

check(
    "EMPTY_DIRECT_ANSWER_NO_TOOL",
    result["ok"] is True
    and result["answer"] == ""
    and scheduler.health_calls == 0,
)


# 6. Non-string direct answer rejected
agent, scheduler, llm = make_agent({
    "decision": "DIRECT_ANSWER",
    "answer": {"message": "hello"},
})
result = agent.run("你好")

check(
    "NON_STRING_ANSWER_REJECTED",
    result["ok"] is False
    and result["error"]["code"]
    == "INVALID_DECISION",
)


# 7. Scheduler exception is isolated
agent, scheduler, llm = make_agent(tool_call())
scheduler.fail_health = True

result = agent.run("检查健康")

check(
    "SCHEDULER_EXCEPTION_HANDLED",
    result["ok"] is False
    and result["tool_response"]["error"]["code"]
    == "TOOL_EXECUTION_FAILED",
)


# 8. Internal exception is not exposed
check(
    "INTERNAL_ERROR_HIDDEN",
    "database-secret" not in json.dumps(result),
)


# 9. Recovery was not executed on failure
check(
    "FAILURE_DOES_NOT_EXECUTE_RECOVERY",
    scheduler.recovery_calls == 0,
)


# 10. Recovery after transient failure
scheduler.fail_health = False
result = agent.run("检查健康")

check(
    "AGENT_RECOVERS_AFTER_FAILURE",
    result["ok"] is True
    and result["tool_response"]["result"][
        "scheduler_health"
    ] == "HEALTHY",
)


# 11. Consecutive queries
result = agent.run("再检查一次健康")

check(
    "CONSECUTIVE_QUERIES_WORK",
    result["ok"] is True
    and scheduler.health_calls == 3,
)


# 12. No recovery executed
check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)


# 13. JSON compatibility
json.dumps(result)

check(
    "RESULT_JSON_COMPATIBLE",
    True,
)


# 14. Invalid user message type
agent, scheduler, llm = make_agent(tool_call())
result = agent.run(123)

check(
    "INVALID_MESSAGE_TYPE_REJECTED",
    result["ok"] is False
    and result["error"]["code"]
    == "INVALID_USER_MESSAGE"
    and llm.calls == 0,
)


print(
    "[TEST] ALL PASS: "
    "Recovery LLM safe agent boundary"
)
