
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


# 场景1：直接回答不应添加 summary
agent = make_agent({
    "type": "DIRECT_ANSWER",
    "answer": "你好",
})
response = agent.ask("你好")

check(
    "DIRECT_ANSWER_UNCHANGED",
    response == {
        "ok": True,
        "type": "DIRECT_ANSWER",
        "answer": "你好",
    },
)


# 场景2：未知 Tool 不应生成 summary
agent = make_agent({
    "type": "TOOL_CALL",
    "tool_name": "unknown_tool",
    "arguments": json.dumps({}),
})
response = agent.ask("调用未知工具")

check(
    "UNKNOWN_TOOL_ERROR",
    response["ok"] is False
    and response["result"]["error"]["code"] == "UNKNOWN_TOOL",
)

check(
    "UNKNOWN_TOOL_NO_SUMMARY",
    "summary" not in response,
)


# 场景3：JOB Tool 参数错误，不应生成 summary
agent = make_agent({
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": json.dumps({"limit": 0}),
})
response = agent.ask("检查JOB")

check(
    "INVALID_LIMIT_ERROR",
    response["ok"] is False
    and response["result"]["error"]["code"] == "INVALID_ARGUMENTS",
)

check(
    "INVALID_LIMIT_NO_SUMMARY",
    "summary" not in response,
)


# 场景4：健康检查 Tool 成功时不应添加 summary
agent = make_agent({
    "type": "TOOL_CALL",
    "tool_name": "get_webhook_notification_recovery_health",
    "arguments": json.dumps({}),
})

# 使用 Mock Dispatcher 返回，隔离真实 Scheduler 依赖
with patch.object(
    agent._dispatcher,
    "dispatch",
    return_value={
        "ok": True,
        "tool_name": "get_webhook_notification_recovery_health",
        "result": {"status": "HEALTHY"},
    },
):
    response = agent.ask("检查通知恢复健康状态")

check(
    "HEALTH_TOOL_OK",
    response["ok"] is True,
)

check(
    "HEALTH_TOOL_NO_SUMMARY",
    "summary" not in response,
)


# 场景5：JOB 元数据异常应被拒绝
agent = make_agent({
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": json.dumps({"limit": 10}),
})

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
    "INVALID_METADATA_REJECTED",
    response["ok"] is False
    and response["error"]["code"] == "INVALID_JOB_SUMMARY",
)

check(
    "INVALID_METADATA_NO_SUMMARY",
    "summary" not in response,
)


print("[TEST] ALL PASS: Agent Summary Boundary")
