
import json
from unittest.mock import patch

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


class FakeLLM:
    def __init__(self, decision):
        self.decision = decision

    def decide(self, message):
        return self.decision


class FakeRepository:
    def get_recent_jobs(self):
        return []


class FakeScheduler:
    pass


def make_agent(decision):
    return OpsPilotMultiToolSafeAgent(
        scheduler=FakeScheduler(),
        job_repository=FakeRepository(),
        llm=FakeLLM(decision),
    )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def tool_decision(name, arguments):
    return {
        "type": "TOOL_CALL",
        "tool_name": name,
        "arguments": json.dumps(arguments),
    }


# 场景1：直接回答
agent = make_agent({
    "type": "DIRECT_ANSWER",
    "answer": "你好",
})
response = agent.ask("你好")

check(
    "DIRECT_ANSWER_NO_AUDIT",
    response["ok"] is True
    and "audit" not in response,
)


# 场景2：未知 Tool
agent = make_agent(
    tool_decision("unknown_tool", {})
)
response = agent.ask("调用未知工具")

check(
    "UNKNOWN_TOOL_NO_AUDIT",
    response["ok"] is False
    and "audit" not in response,
)


# 场景3：非法 JOB 参数
agent = make_agent(
    tool_decision(
        "get_recent_abnormal_jobs",
        {"limit": 0},
    )
)
response = agent.ask("检查JOB")

check(
    "INVALID_LIMIT_NO_AUDIT",
    response["ok"] is False
    and "audit" not in response,
)


# 场景4：健康检查成功
agent = make_agent(
    tool_decision(
        "get_webhook_notification_recovery_health",
        {},
    )
)

with patch.object(
    agent._dispatcher,
    "dispatch",
    return_value={
        "ok": True,
        "tool_name": "get_webhook_notification_recovery_health",
        "result": {"status": "HEALTHY"},
    },
):
    response = agent.ask("检查通知健康状态")

check(
    "HEALTH_TOOL_NO_AUDIT",
    response["ok"] is True
    and "audit" not in response,
)


# 场景5：JOB 统计元数据异常
agent = make_agent(
    tool_decision(
        "get_recent_abnormal_jobs",
        {"limit": 10},
    )
)

with patch.object(
    agent._dispatcher,
    "dispatch",
    return_value={
        "ok": True,
        "tool_name": "get_recent_abnormal_jobs",
        "result": {
            "schema_version": "1.1",
            "tool_name": "get_recent_abnormal_jobs",
            "abnormal_count": 2,
            "total_abnormal_count": 1,
            "returned_count": 2,
            "truncated": False,
            "jobs": [{}, {}],
        },
    },
):
    response = agent.ask("检查JOB")

check(
    "INVALID_METADATA_ERROR",
    response["ok"] is False
    and response["error"]["code"]
    == "INVALID_JOB_SUMMARY",
)

check(
    "INVALID_METADATA_NO_AUDIT",
    "audit" not in response,
)

check(
    "INVALID_METADATA_NO_SUMMARY",
    "summary" not in response,
)


print("[TEST] ALL PASS: Agent Audit Boundary")
