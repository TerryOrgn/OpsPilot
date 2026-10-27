
from unittest.mock import Mock

from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


metrics = WebhookMetrics()
repository = Mock()

repository.create_or_update_alert.side_effect = [
    RuntimeError("MySQL failure #1"),
    RuntimeError("MySQL failure #2"),
    {
        "alert_id": 1001,
        "event_type": "CREATED",
        "alert_status": "OPEN",
        "detect_count": 1,
    },
]

repository.resolve_alert.return_value = True

service = WebhookMetricsAlertService(
    metrics=metrics,
    repository=repository,
    alert_key="TEST-92-53:WEBHOOK_ERROR_RATE",
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


def expect_failure(expected_message):
    try:
        service.run()
    except RuntimeError as exc:
        assert str(exc) == expected_message
        return

    raise AssertionError(
        f"Expected failure: {expected_message}"
    )


# 1. 建立初始基线
baseline = service.run()

assert baseline["monitor_status"] == "BASELINE"

print("[TEST] BASELINE= True")


# 2. 第一个异常窗口：10 次请求，3 次失败
add_events(processed=7, errors=3)

expect_failure("MySQL failure #1")

assert service._pending_operation is not None

print("[TEST] FIRST_ALERT_PENDING= True")


# 3. 数据库故障期间新增 20 次请求
# 其中成功 18 次，失败 2 次
add_events(processed=18, errors=2)

print("[TEST] NEW_REQUESTS_RECORDED= True")


# 4. 第二次数据库写入仍然失败
expect_failure("MySQL failure #2")

assert service._pending_operation is not None

# 此时只有两次数据库写入尝试
assert repository.create_or_update_alert.call_count == 2

print("[TEST] PENDING_RETRY_FAILED= True")


# 5. 数据库恢复
# 第三次写入成功，然后执行积压窗口采样
result = service.run()

assert result["retry_event"] == "CREATED"

assert result["monitor_status"] == "OK"
assert result["db_event"] == "RESOLVED"

print("[TEST] RECOVERY_AND_RESOLUTION= True")


# 6. 验证积压窗口统计结果

# 6. 验证积压窗口统计结果
window = result["window"]

assert window["window_requests"] == 20
assert window["window_errors"] == 2
assert window["window_error_rate"] == 10.0

print("[TEST] BACKLOG_WINDOW_COMPLETE= True")


# 7. 验证原始告警只补偿一次
assert repository.create_or_update_alert.call_count == 3

assert repository.resolve_alert.call_count == 1

print("[TEST] NO_DUPLICATE_PERSISTENCE= True")


# 8. 验证 Pending 已清除
assert result["has_pending"] is False
assert service._pending_operation is None

print("[TEST] PENDING_CLEARED= True")


# 9. 再次运行，不应重复处理积压窗口
next_result = service.run()

assert next_result["monitor_status"] == "INSUFFICIENT_DATA"
assert next_result["retry_event"] == "NO_CHANGE"

assert repository.create_or_update_alert.call_count == 3
assert repository.resolve_alert.call_count == 1

print("[TEST] NO_BACKLOG_REPROCESSING= True")


print(
    "[TEST] ALL PASS: Webhook failure backlog"
)
