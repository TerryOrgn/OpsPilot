
import json

from webhook_notification_recovery_llm_safe_agent import (
    WebhookNotificationRecoveryLLMSafeAgent,
)


TOOL_NAME = "get_webhook_recovery_health"


class FakeScheduler:

    def __init__(self):
        self.health_calls = 0
        self.recovery_calls = 0

    def get_health_snapshot(self):
        self.health_calls += 1

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
        raise AssertionError(
            "Recovery must never execute"
        )


class FakeLLM:

    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = 0

    def decide(self, user_message):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.decision


def make_agent(decision=None, error=None):
    scheduler = FakeScheduler()
    llm = FakeLLM(decision=decision, error=error)

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
        "call_id": "call-001",
    }


# 1. Authorized tool call
agent, scheduler, llm = make_agent(
    decision=tool_call()
)

result = agent.run("检查 Recovery 健康")

assert result["ok"] is True
assert result["decision"] == "TOOL_CALL"
assert result["tool_name"] == TOOL_NAME

print("[TEST] AUTHORIZED_TOOL_CALL= True")


# 2. Read-only health query
assert scheduler.health_calls == 1
assert scheduler.recovery_calls == 0

print("[TEST] READ_ONLY_HEALTH_QUERY= True")


# 3. Schema version preserved
tool_result = result["tool_response"]["result"]

assert tool_result["schema_version"] == "1.0"
assert tool_result["scheduler_health"] == "HEALTHY"

print("[TEST] HEALTH_SCHEMA_PRESERVED= True")


# 4. Direct answer does not call tools
agent, scheduler, llm = make_agent(
    decision={
        "decision": "DIRECT_ANSWER",
        "answer": "你好，我是 OpsPilot。",
    }
)

result = agent.run("你好")

assert result["ok"] is True
assert result["decision"] == "DIRECT_ANSWER"
assert result["tool_response"] is None
assert scheduler.health_calls == 0

print("[TEST] DIRECT_ANSWER_SKIPS_TOOL= True")


# 5. Unknown tool rejected
agent, scheduler, llm = make_agent(
    decision=tool_call(
        name="delete_all_notifications"
    )
)

result = agent.run("删除所有通知")

assert result["ok"] is False
assert result["tool_response"]["error"]["code"] == (
    "UNKNOWN_TOOL"
)
assert scheduler.health_calls == 0

print("[TEST] UNKNOWN_TOOL_REJECTED= True")


# 6. Extra arguments rejected
agent, scheduler, llm = make_agent(
    decision=tool_call(
        arguments='{"force": true}'
    )
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["tool_response"]["error"]["code"] == (
    "UNEXPECTED_ARGUMENTS"
)
assert scheduler.health_calls == 0

print("[TEST] EXTRA_ARGUMENTS_REJECTED= True")


# 7. Invalid JSON rejected
agent, scheduler, llm = make_agent(
    decision=tool_call(arguments="{bad json")
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["tool_response"]["error"]["code"] == (
    "INVALID_JSON"
)
assert scheduler.health_calls == 0

print("[TEST] INVALID_JSON_REJECTED= True")


# 8. Missing tool name rejected
agent, scheduler, llm = make_agent(
    decision={
        "decision": "TOOL_CALL",
        "arguments": "{}",
    }
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["tool_response"]["error"]["code"] == (
    "UNKNOWN_TOOL"
)

print("[TEST] MISSING_TOOL_NAME_REJECTED= True")


# 9. Unsupported decision rejected
agent, scheduler, llm = make_agent(
    decision={
        "decision": "UNSUPPORTED_MULTIPLE_CALLS",
        "tool_count": 2,
    }
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["error"]["code"] == (
    "INVALID_DECISION"
)

print("[TEST] MULTIPLE_CALLS_REJECTED= True")


# 10. Malformed decision rejected
agent, scheduler, llm = make_agent(
    decision=None
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["error"]["code"] == (
    "INVALID_DECISION"
)

print("[TEST] MALFORMED_DECISION_REJECTED= True")


# 11. LLM exception handled
agent, scheduler, llm = make_agent(
    error=RuntimeError("internal-secret")
)

result = agent.run("检查 Recovery")

assert result["ok"] is False
assert result["error"]["code"] == (
    "LLM_DECISION_FAILED"
)
assert "internal-secret" not in str(result)

print("[TEST] LLM_ERROR_HANDLED= True")


# 12. Empty message rejected before LLM
agent, scheduler, llm = make_agent(
    decision=tool_call()
)

result = agent.run("   ")

assert result["ok"] is False
assert result["error"]["code"] == (
    "INVALID_USER_MESSAGE"
)
assert llm.calls == 0

print("[TEST] EMPTY_MESSAGE_REJECTED= True")


# 13. Result JSON compatible
agent, scheduler, llm = make_agent(
    decision=tool_call()
)

result = agent.run("检查 Recovery")

json.dumps(result)

print("[TEST] RESULT_JSON_COMPATIBLE= True")


# 14. Recovery never executed
assert scheduler.recovery_calls == 0

print("[TEST] RECOVERY_NEVER_EXECUTED= True")


print(
    "[TEST] ALL PASS: "
    "Recovery LLM safe agent integration"
)
