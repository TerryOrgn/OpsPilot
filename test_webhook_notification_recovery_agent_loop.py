
import json
from datetime import datetime

from webhook_notification_recovery_agent_loop import (
    FakeLLM,
    WebhookNotificationRecoveryAgentLoop,
)


class FakeScheduler:

    def __init__(self):
        self.health = "HEALTHY"
        self.reason = "RUNNING_NORMALLY"
        self.recovery_status = "EXECUTED"
        self.ready = True
        self.readiness_reason = "READY"

        self.snapshot_calls = 0
        self.run_calls = 0
        self.fail = False

    def get_health_snapshot(self):
        self.snapshot_calls += 1

        if self.fail:
            raise RuntimeError(
                "Simulated internal database failure"
            )

        return {
            "scheduler_health": self.health,
            "health_reason": self.reason,
            "recovery_status": self.recovery_status,
            "ready_for_recovery": self.ready,
            "readiness_reason": self.readiness_reason,
            "total_runs": 5,
            "consecutive_failures": 0,
            "last_success_time": datetime(
                2026, 10, 23, 14, 30, 0
            ),
        }

    def run_once(self):
        self.run_calls += 1
        raise AssertionError(
            "Agent must not execute recovery"
        )


scheduler = FakeScheduler()
llm = FakeLLM()

agent = WebhookNotificationRecoveryAgentLoop(
    scheduler=scheduler,
    llm=llm,
)


# 1. 正常工具调用闭环
result = agent.run("当前 Webhook Recovery 健康吗？")

assert result["ok"] is True
assert result["tool_name"] == (
    "get_webhook_recovery_health"
)

print("[TEST] NORMAL_AGENT_LOOP= True")


# 2. 正确调用工具
assert result["tool_response"]["ok"] is True
assert scheduler.snapshot_calls == 1

print("[TEST] TOOL_CALLED= True")


# 3. 最终回答包含健康状态
assert "健康" in result["answer"]
assert "EXECUTED" in result["answer"]

print("[TEST] HEALTH_ANSWER_GENERATED= True")


# 4. 最终结果可序列化
encoded = json.dumps(result, ensure_ascii=False)
decoded = json.loads(encoded)

assert decoded == result

print("[TEST] AGENT_RESULT_JSON_COMPATIBLE= True")


# 5. 模拟 LLM 调用计数
assert llm.tool_requests == 1
assert llm.answer_requests == 1

print("[TEST] LLM_CALL_COUNTS= True")


# 6. DEGRADED 状态回答
scheduler.health = "DEGRADED"
scheduler.reason = "RECENT_FAILURES"

result = agent.run("恢复调度器状态如何？")

assert "降级" in result["answer"]

print("[TEST] DEGRADED_ANSWER= True")


# 7. UNHEALTHY 状态回答
scheduler.health = "UNHEALTHY"
scheduler.reason = "TOO_MANY_FAILURES"
scheduler.recovery_status = "FAILED"
scheduler.ready = False
scheduler.readiness_reason = (
    "SCHEDULER_UNHEALTHY"
)

result = agent.run("现在恢复任务正常吗？")

assert "不健康" in result["answer"]
assert "不满足 Recovery 就绪条件" in (
    result["answer"]
)

print("[TEST] UNHEALTHY_ANSWER= True")


# 8. 工具执行失败时返回错误回答
scheduler.fail = True

result = agent.run("检查 Webhook Recovery 状态")


assert result["ok"] is False
assert "TOOL_EXECUTION_FAILED" in result["answer"]

print("[TEST] TOOL_FAILURE_ANSWER= True")


# 9. 不暴露内部异常
encoded = json.dumps(result, ensure_ascii=False)

assert "database failure" not in encoded.lower()
assert "RuntimeError" not in encoded

print("[TEST] INTERNAL_ERROR_HIDDEN= True")


# 10. 空用户输入被拒绝
before = scheduler.snapshot_calls

result = agent.run("   ")

assert result["ok"] is False
assert result["error"]["code"] == (
    "INVALID_USER_MESSAGE"
)
assert scheduler.snapshot_calls == before

print("[TEST] EMPTY_MESSAGE_REJECTED= True")


# 11. Recovery 从未执行
assert scheduler.run_calls == 0

print("[TEST] RECOVERY_NEVER_EXECUTED= True")


# 12. 故障恢复后可正常查询
scheduler.fail = False
scheduler.health = "HEALTHY"
scheduler.reason = "RUNNING_NORMALLY"
scheduler.recovery_status = "EXECUTED"
scheduler.ready = True
scheduler.readiness_reason = "READY"

result = agent.run("Webhook Recovery 现在健康吗？")

assert result["ok"] is True
assert result["decision"] == "TOOL_CALL"
assert result["tool_response"]["ok"] is True
assert "健康" in result["answer"]

print("[TEST] AGENT_RECOVERED= True")


# 13. 结果包含 Schema Version
assert result["tool_response"]["result"][
    "schema_version"
] == "1.0"

print("[TEST] SCHEMA_VERSION_PRESERVED= True")


# 14. 最终只读检查
assert scheduler.run_calls == 0

print("[TEST] FINAL_READ_ONLY= True")


# 15. 输出最终回答
print("[INFO] FINAL_ANSWER=", result["answer"])

assert "Webhook Recovery" in result["answer"]

print("[TEST] FINAL_ANSWER_VALID= True")


print(
    "[TEST] ALL PASS: "
    "Recovery Agent tool calling loop"
)
