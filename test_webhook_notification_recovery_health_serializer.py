
import json
from copy import deepcopy
from datetime import datetime, timezone

from webhook_notification_recovery_health_serializer import (
    WebhookNotificationRecoveryHealthSerializer,
)


serializer = WebhookNotificationRecoveryHealthSerializer()


def make_snapshot():
    return {
        "scheduler_health": "HEALTHY",
        "health_reason": "RUNNING_NORMALLY",
        "recovery_status": "EXECUTED",
        "ready_for_recovery": True,
        "readiness_reason": "READY",
        "total_runs": 4,
        "consecutive_failures": 0,
        "last_success_time": datetime(
            2026, 10, 23, 14, 0, 0
        ),
    }


def expect_error(snapshot, exception_type):
    try:
        serializer.serialize(snapshot)
    except exception_type:
        return
    raise AssertionError(
        f"Expected {exception_type.__name__}"
    )


# 1. 正常序列化
snapshot = make_snapshot()
result = serializer.serialize(snapshot)

assert result["scheduler_health"] == "HEALTHY"
assert result["recovery_status"] == "EXECUTED"
print("[TEST] NORMAL_SERIALIZATION= True")


# 2. JSON 可序列化
encoded = json.dumps(result)
decoded = json.loads(encoded)

assert decoded == result
print("[TEST] JSON_COMPATIBLE= True")


# 3. naive datetime 不伪装 UTC
assert result["last_success_time"] == (
    "2026-10-23T14:00:00.000000"
)
print("[TEST] NAIVE_DATETIME_PRESERVED= True")


# 4. 带时区时间统一为 UTC
snapshot = make_snapshot()
snapshot["last_success_time"] = datetime(
    2026, 10, 23, 14, 0, 0,
    tzinfo=timezone.utc,
)

result = serializer.serialize(snapshot)

assert result["last_success_time"] == (
    "2026-10-23T14:00:00.000000Z"
)
print("[TEST] UTC_DATETIME= True")


# 5. 无成功时间
snapshot = make_snapshot()
snapshot["scheduler_health"] = "DEGRADED"
snapshot["health_reason"] = "NO_SUCCESS_YET"
snapshot["recovery_status"] = "NOT_RUN"
snapshot["total_runs"] = 0
snapshot["last_success_time"] = None

result = serializer.serialize(snapshot)

assert result["last_success_time"] is None
print("[TEST] NULL_TIMESTAMP= True")


# 6. 不修改原始数据
snapshot = make_snapshot()
before = deepcopy(snapshot)

serializer.serialize(snapshot)

assert snapshot == before
print("[TEST] INPUT_NOT_MUTATED= True")


# 7. 拒绝非法健康状态
snapshot = make_snapshot()
snapshot["scheduler_health"] = "UNKNOWN"

expect_error(snapshot, ValueError)
print("[TEST] INVALID_HEALTH_REJECTED= True")


# 8. 拒绝非法执行状态
snapshot = make_snapshot()
snapshot["recovery_status"] = "UNKNOWN"

expect_error(snapshot, ValueError)
print("[TEST] INVALID_RECOVERY_REJECTED= True")


# 9. 拒绝不一致的就绪状态
snapshot = make_snapshot()
snapshot["ready_for_recovery"] = False

expect_error(snapshot, ValueError)
print("[TEST] INCONSISTENT_READINESS_REJECTED= True")


# 10. 拒绝缺失字段
snapshot = make_snapshot()
del snapshot["recovery_status"]

expect_error(snapshot, ValueError)
print("[TEST] MISSING_FIELD_REJECTED= True")


print(
    "[TEST] ALL PASS: "
    "Recovery health snapshot serialization"
)
