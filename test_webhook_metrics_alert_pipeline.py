
from webhook_metrics import WebhookMetrics
from webhook_metrics_alert_pipeline import (
    WebhookMetricsAlertPipeline,
)


metrics = WebhookMetrics()

pipeline = WebhookMetricsAlertPipeline(
    metrics=metrics,
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


def check(name, expected_status, expected_event, expected_state):
    result = pipeline.run()

    assert result["monitor_status"] == expected_status, result
    assert result["event"] == expected_event, result
    assert result["current_state"] == expected_state, result

    print(f"[TEST] {name}= True")


# 1. 首次运行：建立采样基线
check(
    "FIRST_BASELINE",
    "BASELINE",
    "NO_CHANGE",
    "NORMAL",
)


# 2. 首次异常：10 次请求，3 次错误
add_events(processed=7, errors=3)

check(
    "FIRST_ALERT",
    "ALERT",
    "NEW_ALERT",
    "FIRING",
)


# 3. 持续异常：不重复产生新告警
add_events(processed=8, errors=2)

check(
    "DUPLICATE_ALERT",
    "ALERT",
    "DUPLICATE",
    "FIRING",
)


# 4. 数据不足：不能误恢复
add_events(processed=3, errors=0)

check(
    "INSUFFICIENT_DATA_HOLDS",
    "INSUFFICIENT_DATA",
    "NO_CHANGE",
    "FIRING",
)


# 5. 正常窗口：触发恢复
add_events(processed=10, errors=0)

check(
    "ALERT_RESOLVED",
    "OK",
    "RESOLVED",
    "NORMAL",
)


# 6. 持续正常：不产生新事件
add_events(processed=10, errors=0)

check(
    "NORMAL_NO_CHANGE",
    "OK",
    "NO_CHANGE",
    "NORMAL",
)


# 7. 恢复后再次异常
add_events(processed=6, errors=4)

check(
    "ALERT_AGAIN",
    "ALERT",
    "NEW_ALERT",
    "FIRING",
)


# 8. 计数器重置：保持告警状态
metrics.reset()

check(
    "RESET_HOLDS",
    "RESET",
    "NO_CHANGE",
    "FIRING",
)


# 9. 重置后正常窗口：恢复告警
add_events(processed=10, errors=0)

check(
    "AFTER_RESET_RESOLVED",
    "OK",
    "RESOLVED",
    "NORMAL",
)


assert pipeline.current_alert_state() == "NORMAL"

print("[TEST] FINAL_STATE_NORMAL= True")
print("[TEST] ALL PASS: Webhook metrics alert pipeline")
