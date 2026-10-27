
from unittest.mock import Mock

from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


metrics = WebhookMetrics()
repository = Mock()

# 前三次写入失败，第四次成功
repository.create_or_update_alert.side_effect = [
    RuntimeError("MySQL failure #1"),
    RuntimeError("MySQL failure #2"),
    RuntimeError("MySQL failure #3"),
    {
        "alert_id": 1001,
        "event_type": "CREATED",
        "alert_status": "OPEN",
        "detect_count": 1,
    },
]

repository.resolve_alert.return_value = False

service = WebhookMetricsAlertService(
    metrics=metrics,
    repository=repository,
    alert_key="TEST-92-52:WEBHOOK_ERROR_RATE",
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


# 1. 建立初始采样基线
baseline = service.run()

assert baseline["monitor_status"] == "BASELINE"

print("[TEST] BASELINE= True")


# 2. 产生异常窗口：错误率 30%
add_events(processed=7, errors=3)


# 3. 连续三次写入失败
for attempt in range(1, 4):

    try:
        service.run()
        raise AssertionError(
            f"Expected MySQL failure #{attempt}"
        )

    except RuntimeError as exc:
        assert str(exc) == f"MySQL failure #{attempt}"

    # Pending 不能丢失
    assert service._pending_operation is not None
    assert service._pending_operation["type"] == "ALERT"

    # 已尝试写入的次数必须准确
    assert (
        repository.create_or_update_alert.call_count
        == attempt
    )

    print(
        f"[TEST] FAILURE_{attempt}_PENDING_RETAINED= True"
    )


# 4. 第四次运行，数据库恢复
result = service.run()

assert result["retry_event"] == "CREATED"
assert result["has_pending"] is False

assert (
    repository.create_or_update_alert.call_count
    == 4
)

print("[TEST] FOURTH_ATTEMPT_SUCCESS= True")


# 5. 第四次重试成功后，没有新请求
# 因此不应该重新处理旧窗口
assert result["monitor_status"] == "INSUFFICIENT_DATA"
assert result["db_event"] == "NO_CHANGE"

print("[TEST] OLD_WINDOW_NOT_REPROCESSED= True")


# 6. 再次执行，不应该重复补偿
result = service.run()

assert result["retry_event"] == "NO_CHANGE"
assert result["has_pending"] is False

assert (
    repository.create_or_update_alert.call_count
    == 4
)

print("[TEST] NO_DUPLICATE_RETRY= True")


# 7. 验证失败期间没有产生新的监控采样
# 此处检查 Pipeline 的累计采样行为：
# 失败期间没有新增请求，恢复后没有重复处理旧窗口。
assert service._pending_operation is None

print("[TEST] PENDING_CLEARED= True")


print(
    "[TEST] ALL PASS: Webhook consecutive DB failures"
)
