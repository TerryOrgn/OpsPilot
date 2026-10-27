
from unittest.mock import Mock

from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


metrics = WebhookMetrics()

repository = Mock()

repository.create_or_update_alert.side_effect = RuntimeError(
    "Simulated MySQL connection failure"
)

repository.resolve_alert.return_value = False


service = WebhookMetricsAlertService(
    metrics=metrics,
    repository=repository,
    alert_key="TEST-92-50:WEBHOOK_ERROR_RATE",
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


# 1. 建立采样基线
baseline = service.run()

assert baseline["monitor_status"] == "BASELINE"
assert baseline["db_event"] == "NO_CHANGE"

print("[TEST] BASELINE= True")


# 2. 产生异常窗口：10 次请求，3 次失败
add_events(processed=7, errors=3)

failed = False

try:
    service.run()

except RuntimeError as exc:
    assert "Simulated MySQL" in str(exc)
    failed = True

assert failed

print("[TEST] DB_FAILURE_PROPAGATED= True")


# 3. 模拟 MySQL 恢复
repository.create_or_update_alert.side_effect = None

repository.create_or_update_alert.return_value = {
    "alert_id": 1001,
    "event_type": "CREATED",
    "alert_status": "OPEN",
    "detect_count": 1,
}

print("[TEST] DB_RECOVERED= True")


# 4. 不产生新请求，直接再次执行
retry_result = service.run()

# 当前 Pipeline 会重新采样。
# 上次异常窗口已经被消费，
# 因此本次请求量为 0。
assert retry_result["monitor_status"] == "INSUFFICIENT_DATA"
assert retry_result["db_event"] == "NO_CHANGE"

print("[TEST] RETRY_WINDOW_INSUFFICIENT= True")


# 5. 数据库写入仅尝试过一次
assert repository.create_or_update_alert.call_count == 1

print("[TEST] ALERT_NOT_RETRIED= True")


# 6. 再次出现异常窗口
add_events(processed=7, errors=3)

new_result = service.run()

assert new_result["monitor_status"] == "ALERT"
assert new_result["db_event"] == "CREATED"

print("[TEST] NEXT_ALERT_WINDOW_PERSISTED= True")


print("[TEST] ALL PASS: Webhook metrics DB failure diagnosis")
