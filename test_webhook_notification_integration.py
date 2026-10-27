
from unittest.mock import Mock

from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


def add_events(metrics, processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


def create_service(metrics, repository):
    return WebhookMetricsAlertService(
        metrics=metrics,
        repository=repository,
        alert_key="TEST-92-55:WEBHOOK_ERROR_RATE",
        min_requests=10,
        error_threshold=20.0,
    )


# ============================================
# 场景 A：正常告警生命周期
# ============================================

metrics = WebhookMetrics()
repository = Mock()

repository.create_or_update_alert.side_effect = [
    {
        "alert_id": 1001,
        "event_type": "CREATED",
    },
    {
        "alert_id": 1001,
        "event_type": "DUPLICATE",
    },
]

repository.resolve_alert.return_value = True

service = create_service(metrics, repository)

# 1. 首次采样
result = service.run()

assert result["notification_action"] == "SKIP"

print("[TEST] BASELINE_SKIP= True")


# 2. 首次异常
add_events(metrics, processed=7, errors=3)

result = service.run()

assert result["db_event"] == "CREATED"
assert result["notification_action"] == "SEND"
assert result["notification_reason"] == "NEW_ACTIVE_ALERT"

print("[TEST] CREATED_SEND= True")


# 3. 持续异常
add_events(metrics, processed=8, errors=2)

result = service.run()

assert result["db_event"] == "DUPLICATE"
assert result["notification_action"] == "SKIP"

print("[TEST] DUPLICATE_SKIP= True")


# 4. 正常恢复
add_events(metrics, processed=10, errors=0)

result = service.run()

assert result["db_event"] == "RESOLVED"
assert result["notification_action"] == "SEND"
assert result["notification_reason"] == "ALERT_RESOLVED"

print("[TEST] RESOLVED_SEND= True")


# ============================================
# 场景 B：数据库故障后同次恢复
# ============================================

metrics2 = WebhookMetrics()
repository2 = Mock()

repository2.create_or_update_alert.side_effect = [
    RuntimeError("Simulated MySQL failure"),
    {
        "alert_id": 2001,
        "event_type": "CREATED",
    },
]

repository2.resolve_alert.return_value = True

service2 = create_service(metrics2, repository2)

# 5. 建立基线
result = service2.run()

assert result["notification_action"] == "SKIP"

print("[TEST] RECOVERY_BASELINE_SKIP= True")


# 6. 首次异常，数据库写入失败
add_events(metrics2, processed=7, errors=3)

try:
    service2.run()
    raise AssertionError("Expected MySQL failure")

except RuntimeError as exc:
    assert "Simulated MySQL failure" in str(exc)

assert service2._pending_operation is not None

print("[TEST] FAILURE_PENDING_SAVED= True")


# 7. 故障期间积累正常请求
add_events(metrics2, processed=10, errors=0)

# 8. 数据库恢复后，先补写异常，再关闭告警
result = service2.run()

assert result["retry_event"] == "CREATED"
assert result["db_event"] == "RESOLVED"

assert result["notification_action"] == "SUPPRESS"
assert (
    result["notification_reason"]
    == "RECOVERED_IN_SAME_RUN"
)

assert result["notification_events"] == [
    "CREATED",
    "RESOLVED",
]

print("[TEST] RECOVERED_SAME_RUN_SUPPRESS= True")


# 9. Pending 已清除
assert result["has_pending"] is False

print("[TEST] PENDING_CLEARED= True")


# 10. 再次运行，不重复通知
result = service2.run()

assert result["notification_action"] == "SKIP"
assert result["retry_event"] == "NO_CHANGE"

print("[TEST] NO_DUPLICATE_NOTIFICATION= True")


print(
    "[TEST] ALL PASS: Webhook notification integration"
)
