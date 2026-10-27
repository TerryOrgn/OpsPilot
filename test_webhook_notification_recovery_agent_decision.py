
import json
from datetime import datetime

from webhook_notification_recovery_agent_loop import (
    FakeLLM,
    WebhookNotificationRecoveryAgentLoop,
)


class FakeScheduler:

    def __init__(self):
        self.snapshot_calls = 0
        self.run_calls = 0

    def get_health_snapshot(self):
        self.snapshot_calls += 1

        return {
            "scheduler_health": "HEALTHY",
            "health_reason": "RUNNING_NORMALLY",
            "recovery_status": "EXECUTED",
            "ready_for_recovery": True,
            "readiness_reason": "READY",
            "total_runs": 5,
            "consecutive_failures": 0,
            "last_success_time": datetime(
                2026, 10, 23, 14, 30, 0
            ),
        }

    def run_once(self):
        self.run_calls += 1
        raise AssertionError(
            "Recovery must not be executed"
        )


scheduler = FakeScheduler()
llm = FakeLLM()

agent = WebhookNotificationRecoveryAgentLoop(
    scheduler=scheduler,
    llm=llm,
)


# 1. Recovery 健康查询
result = agent.run("Recovery 健康吗？")

assert result["ok"] is True
assert result["decision"] == "TOOL_CALL"
assert scheduler.snapshot_calls == 1

print("[TEST] HEALTH_QUERY_CALLS_TOOL= True")


# 2. Webhook Recovery 状态查询
result = agent.run("检查 Webhook Recovery 状态")

assert result["decision"] == "TOOL_CALL"
assert scheduler.snapshot_calls == 2

print("[TEST] STATUS_QUERY_CALLS_TOOL= True")


# 3. 普通问候不调用工具
before = scheduler.snapshot_calls

result = agent.run("你好")

assert result["decision"] == "DIRECT_ANSWER"
assert result["tool_name"] is None
assert result["tool_response"] is None
assert scheduler.snapshot_calls == before

print("[TEST] GREETING_NO_TOOL= True")


# 4. 无关问题不调用工具
before = scheduler.snapshot_calls

result = agent.run("今天天气怎么样？")

assert result["decision"] == "DIRECT_ANSWER"
assert scheduler.snapshot_calls == before

print("[TEST] UNRELATED_QUERY_NO_TOOL= True")


# 5. 删除请求被拒绝
before = scheduler.snapshot_calls

result = agent.run("删除所有通知")

assert result["decision"] == "DIRECT_ANSWER"
assert "不允许" in result["answer"]
assert scheduler.snapshot_calls == before

print("[TEST] DELETE_REQUEST_REJECTED= True")


# 6. 英文删除请求被拒绝
result = agent.run(
    "Delete all webhook notifications"
)

assert result["decision"] == "DIRECT_ANSWER"
assert "不允许" in result["answer"]

print("[TEST] ENGLISH_DELETE_REJECTED= True")


# 7. 英文健康查询
result = agent.run(
    "Check webhook recovery health"
)

assert result["decision"] == "TOOL_CALL"
assert scheduler.snapshot_calls == 3

print("[TEST] ENGLISH_HEALTH_QUERY= True")


# 8. 健康查询包含回答
assert "健康" in result["answer"]
assert "EXECUTED" in result["answer"]

print("[TEST] HEALTH_ANSWER_VALID= True")


# 9. 直接回答不执行 generate_answer()
before_answers = llm.answer_requests

agent.run("你好")

assert llm.answer_requests == before_answers

print("[TEST] DIRECT_ANSWER_SKIPS_TOOL_RESULT= True")


# 10. 无效用户输入
before_calls = scheduler.snapshot_calls
before_requests = llm.tool_requests

result = agent.run("   ")

assert result["ok"] is False
assert result["error"]["code"] == (
    "INVALID_USER_MESSAGE"
)
assert scheduler.snapshot_calls == before_calls
assert llm.tool_requests == before_requests

print("[TEST] EMPTY_MESSAGE_REJECTED= True")


# 11. 工具调用计数
assert llm.answer_requests == 3

print("[TEST] TOOL_ANSWER_COUNT= True")


# 12. 所有结果均可 JSON 序列化
result = agent.run("你好")

encoded = json.dumps(result, ensure_ascii=False)
decoded = json.loads(encoded)

assert decoded == result

print("[TEST] DIRECT_ANSWER_JSON_COMPATIBLE= True")


# 13. Recovery 从未执行
assert scheduler.run_calls == 0

print("[TEST] RECOVERY_NEVER_EXECUTED= True")


# 14. 最终调用统计
assert scheduler.snapshot_calls == 3
assert scheduler.run_calls == 0

print("[TEST] FINAL_CALL_COUNTS= True")


print(
    "[TEST] ALL PASS: "
    "Recovery Agent tool calling decision"
)
