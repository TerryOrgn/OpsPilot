
from datetime import datetime, timedelta

from webhook_notification_recovery_health import (
    WebhookNotificationRecoveryHealth,
)


health = WebhookNotificationRecoveryHealth(
    failure_threshold=3,
    stale_seconds=300,
)

now = datetime(2026, 10, 23, 14, 0, 0)


def check(name, stats, expected_status, expected_reason):
    result = health.evaluate(
        stats,
        now=now,
    )

    assert result["status"] == expected_status
    assert result["reason"] == expected_reason

    print(f"[TEST] {name}= True")


# 1. 正常运行
check(
    "HEALTHY",
    {
        "consecutive_failures": 0,
        "last_success_time": now - timedelta(seconds=30),
    },
    "HEALTHY",
    "RUNNING_NORMALLY",
)


# 2. 首次启动，无成功记录
check(
    "NO_SUCCESS_YET",
    {
        "consecutive_failures": 0,
        "last_success_time": None,
    },
    "DEGRADED",
    "NO_SUCCESS_YET",
)


# 3. 连续失败一次
check(
    "ONE_FAILURE",
    {
        "consecutive_failures": 1,
        "last_success_time": now - timedelta(seconds=30),
    },
    "DEGRADED",
    "RECENT_FAILURES",
)


# 4. 连续失败两次
check(
    "TWO_FAILURES",
    {
        "consecutive_failures": 2,
        "last_success_time": now - timedelta(seconds=30),
    },
    "DEGRADED",
    "RECENT_FAILURES",
)


# 5. 连续失败三次
check(
    "THREE_FAILURES",
    {
        "consecutive_failures": 3,
        "last_success_time": now - timedelta(seconds=30),
    },
    "UNHEALTHY",
    "TOO_MANY_FAILURES",
)


# 6. 成功记录过期
check(
    "STALE_SUCCESS",
    {
        "consecutive_failures": 0,
        "last_success_time": now - timedelta(seconds=301),
    },
    "UNHEALTHY",
    "SUCCESS_TOO_OLD",
)


# 7. 恰好五分钟
check(
    "BOUNDARY_300_SECONDS",
    {
        "consecutive_failures": 0,
        "last_success_time": now - timedelta(seconds=300),
    },
    "HEALTHY",
    "RUNNING_NORMALLY",
)


# 8. 恢复后健康
check(
    "RECOVERED_HEALTHY",
    {
        "consecutive_failures": 0,
        "last_success_time": now,
    },
    "HEALTHY",
    "RUNNING_NORMALLY",
)


# 9. 非法失败阈值
try:
    WebhookNotificationRecoveryHealth(
        failure_threshold=0
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid failure threshold must be rejected"
    )

print("[TEST] INVALID_FAILURE_THRESHOLD= True")


# 10. 非法成功过期时间
try:
    WebhookNotificationRecoveryHealth(
        stale_seconds=0
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid stale_seconds must be rejected"
    )

print("[TEST] INVALID_STALE_SECONDS= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery health"
)
