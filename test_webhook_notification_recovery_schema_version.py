
import json
from copy import deepcopy
from datetime import datetime

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
        "total_runs": 5,
        "consecutive_failures": 0,
        "last_success_time": datetime(
            2026, 10, 23, 14, 10, 20
        ),
    }


def expect_version_error(version):
    try:
        serializer.serialize(
            make_snapshot(),
            schema_version=version,
        )
    except ValueError:
        return

    raise AssertionError(
        f"Version {version!r} must be rejected"
    )


# 1. 默认版本
result = serializer.serialize(make_snapshot())

assert result["schema_version"] == "1.0"
print("[TEST] DEFAULT_VERSION= True")


# 2. 显式指定版本
result = serializer.serialize(
    make_snapshot(),
    schema_version="1.0",
)

assert result["schema_version"] == "1.0"
print("[TEST] EXPLICIT_VERSION= True")


# 3. 版本常量正确
assert serializer.SCHEMA_VERSION == "1.0"
assert serializer.SUPPORTED_VERSIONS == frozenset({"1.0"})

print("[TEST] VERSION_CONSTANTS= True")


# 4. 原有字段全部保留
snapshot = make_snapshot()
result = serializer.serialize(snapshot)

assert set(result.keys()) == (
    set(snapshot.keys()) | {"schema_version"}
)

print("[TEST] LEGACY_FIELDS_PRESERVED= True")


# 5. 原有字段含义不变
assert result["scheduler_health"] == "HEALTHY"
assert result["recovery_status"] == "EXECUTED"
assert result["ready_for_recovery"] is True
assert result["total_runs"] == 5

print("[TEST] LEGACY_VALUES_PRESERVED= True")


# 6. JSON 编码与解码
encoded = json.dumps(result)
decoded = json.loads(encoded)

assert decoded == result
assert decoded["schema_version"] == "1.0"

print("[TEST] VERSIONED_JSON_COMPATIBLE= True")


# 7. 不修改原始快照
snapshot = make_snapshot()
before = deepcopy(snapshot)

serializer.serialize(snapshot)

assert snapshot == before
assert "schema_version" not in snapshot

print("[TEST] INPUT_NOT_MUTATED= True")


# 8. 拒绝未来未知版本
expect_version_error("2.0")

print("[TEST] FUTURE_VERSION_REJECTED= True")


# 9. 拒绝非法版本
expect_version_error("invalid")

print("[TEST] INVALID_VERSION_REJECTED= True")


# 10. 拒绝非字符串版本
expect_version_error(1.0)

print("[TEST] NON_STRING_VERSION_REJECTED= True")


# 11. 拒绝空版本
expect_version_error("")

print("[TEST] EMPTY_VERSION_REJECTED= True")


# 12. 版本字段不破坏时间序列化
result = serializer.serialize(make_snapshot())

assert result["last_success_time"] == (
    "2026-10-23T14:10:20.000000"
)

print("[TEST] TIMESTAMP_COMPATIBLE= True")


print(
    "[TEST] ALL PASS: "
    "Recovery health schema versioning"
)
