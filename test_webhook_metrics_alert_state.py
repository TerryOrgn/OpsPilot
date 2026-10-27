
from webhook_metrics_alert_state import (
    WebhookMetricsAlertState,
)


state = WebhookMetricsAlertState()


def check(name, monitor_status, expected_event, expected_state):
    result = state.update(monitor_status)

    assert result["event"] == expected_event, result
    assert result["current_state"] == expected_state, result

    print(f"[TEST] {name}= True")


# 1. 初始状态
assert state.current_state() == "NORMAL"
print("[TEST] INITIAL_NORMAL= True")


# 2. 首次异常
check(
    "FIRST_ALERT",
    "ALERT",
    "NEW_ALERT",
    "FIRING",
)


# 3. 持续异常不重复告警
check(
    "DUPLICATE_ALERT",
    "ALERT",
    "DUPLICATE",
    "FIRING",
)


# 4. 数据不足不能关闭告警
check(
    "INSUFFICIENT_DATA_HOLDS",
    "INSUFFICIENT_DATA",
    "NO_CHANGE",
    "FIRING",
)


# 5. 计数器重置不能关闭告警
check(
    "RESET_HOLDS",
    "RESET",
    "NO_CHANGE",
    "FIRING",
)


# 6. 恢复正常
check(
    "ALERT_RESOLVED",
    "OK",
    "RESOLVED",
    "NORMAL",
)


# 7. 持续正常不产生新事件
check(
    "NORMAL_NO_CHANGE",
    "OK",
    "NO_CHANGE",
    "NORMAL",
)


# 8. 恢复后再次异常，产生新告警
check(
    "ALERT_AGAIN",
    "ALERT",
    "NEW_ALERT",
    "FIRING",
)


# 9. 非法状态必须拒绝
try:
    state.update("UNKNOWN")
except ValueError:
    print("[TEST] INVALID_STATUS_REJECTED= True")
else:
    raise AssertionError("Invalid status must be rejected")


print("[TEST] ALL PASS: Webhook metrics alert state")
