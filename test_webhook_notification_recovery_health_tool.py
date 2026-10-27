
import json
from copy import deepcopy
from datetime import datetime

from webhook_notification_recovery_health_tool import (
    WebhookNotificationRecoveryHealthTool,
    get_recovery_health_tool,
)


class FakeScheduler:

    def __init__(self):
        self.snapshot_calls = 0
        self.run_calls = 0

        self.snapshot = {
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

    def get_health_snapshot(self):
        self.snapshot_calls += 1
        return deepcopy(self.snapshot)

    def run_once(self):
        self.run_calls += 1
        raise AssertionError(
            "Read-only tool must not execute recovery"
        )


scheduler = FakeScheduler()

tool = WebhookNotificationRecoveryHealthTool(
    scheduler=scheduler
)


# 1. 工具名称
assert tool.TOOL_NAME == "get_webhook_recovery_health"
print("[TEST] TOOL_NAME_VALID= True")


# 2. 工具描述
assert "read-only" in tool.TOOL_DESCRIPTION
print("[TEST] TOOL_DESCRIPTION_VALID= True")


# 3. 正常执行
result = tool.execute()

assert result["scheduler_health"] == "HEALTHY"
assert result["recovery_status"] == "EXECUTED"
assert result["ready_for_recovery"] is True

print("[TEST] TOOL_EXECUTION= True")


# 4. Schema Version
assert result["schema_version"] == "1.0"
print("[TEST] SCHEMA_VERSION= True")


# 5. JSON 可序列化
encoded = json.dumps(result)
decoded = json.loads(encoded)

assert decoded == result
print("[TEST] JSON_COMPATIBLE= True")


# 6. 时间序列化
assert result["last_success_time"] == (
    "2026-10-23T14:30:00.000000"
)

print("[TEST] TIMESTAMP_SERIALIZED= True")


# 7. 不执行 Recovery
assert scheduler.run_calls == 0
print("[TEST] RECOVERY_NOT_EXECUTED= True")


# 8. 原始快照不变
before = deepcopy(scheduler.snapshot)

tool.execute()

assert scheduler.snapshot == before
print("[TEST] SNAPSHOT_NOT_MUTATED= True")


# 9. 每次调用都读取新快照
before_calls = scheduler.snapshot_calls

tool.execute()

assert scheduler.snapshot_calls == before_calls + 1

print("[TEST] FRESH_SNAPSHOT_PER_CALL= True")


# 10. 通过函数入口调用
result = get_recovery_health_tool(scheduler)

assert result["schema_version"] == "1.0"
assert result["scheduler_health"] == "HEALTHY"

print("[TEST] FUNCTION_ENTRYPOINT= True")


# 11. 拒绝缺少 Scheduler
try:
    WebhookNotificationRecoveryHealthTool(None)
except ValueError:
    pass
else:
    raise AssertionError(
        "Missing scheduler must be rejected"
    )

print("[TEST] MISSING_SCHEDULER_REJECTED= True")


# 12. 不暴露内部对象
result = tool.execute()

assert "_scheduler" not in result
assert "_serializer" not in result
assert "worker" not in result
assert "repository" not in result

print("[TEST] INTERNAL_OBJECTS_NOT_EXPOSED= True")


# 13. 最终确认只读
assert scheduler.run_calls == 0

print("[TEST] FINAL_READ_ONLY= True")


print(
    "[TEST] ALL PASS: "
    "Recovery health Agent tool adapter"
)
