
from unittest.mock import Mock

from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


metrics = WebhookMetrics()
repository = Mock()

repository.resolve_alert.return_value = False

repository.create_or_update_alert.side_effect = RuntimeError(
    "Simulated MySQL connection failure"
)

service = WebhookMetricsAlertService(
    metrics=metrics,
    repository=repository,
    alert_key="TEST-92-51:WEBHOOK_ERROR_RATE",
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


# 1. 首次采样
baseline = service.run()

assert baseline["monitor_status"] == "BASELINE"

print("[TEST] BASELINE= True")


# 2. 产生异常窗口
add_events(processed=7, errors=3)

try:
    service.run()
    raise AssertionError("Expected MySQL failure")

except RuntimeError as exc:
    assert "Simulated MySQL" in str(exc)

assert service._pending_operation is not None
assert service._pending_operation["type"] == "ALERT"

print("[TEST] FAILURE_PENDING_SAVED= True")


# 3. 模拟数据库恢复
repository.create_or_update_alert.side_effect = None

repository.create_or_update_alert.return_value = {
    "alert_id": 1001,
    "event_type": "CREATED",
    "alert_status": "OPEN",
    "detect_count": 1,
}


# 4. 没有新请求，直接重试
result = service.run()

assert result["retry_event"] == "CREATED"
assert result["monitor_status"] == "INSUFFICIENT_DATA"
assert result["db_event"] == "NO_CHANGE"
assert result["has_pending"] is False

print("[TEST] PENDING_RETRIED= True")


# 5. 验证原始操作确实执行两次
assert repository.create_or_update_alert.call_count == 2

print("[TEST] RETRY_CALL_COUNT= True")


# 6. 再次运行，不应重复补偿
result = service.run()

assert result["retry_event"] == "NO_CHANGE"
assert result["has_pending"] is False

assert repository.create_or_update_alert.call_count == 2

print("[TEST] NO_EXTRA_RETRY= True")


# 7. 新异常窗口仍可正常处理
repository.create_or_update_alert.return_value = {
    "alert_id": 1001,
    "event_type": "DUPLICATE",
    "alert_status": "OPEN",
    "detect_count": 2,
}

add_events(processed=7, errors=3)

result = service.run()

assert result["monitor_status"] == "ALERT"
assert result["db_event"] == "DUPLICATE"
assert result["retry_event"] == "NO_CHANGE"

print("[TEST] NEW_WINDOW_PROCESSED= True")


# 8. 验证补偿机制已清空
assert service._pending_operation is None

print("[TEST] PENDING_CLEARED= True")

print("[TEST] ALL PASS: Webhook pending retry")
