
from webhook_metrics import WebhookMetrics
from webhook_metrics_monitor import WebhookMetricsMonitor


metrics = WebhookMetrics()

monitor = WebhookMetricsMonitor(
    metrics=metrics,
    min_requests=10,
    error_threshold=20.0,
)


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


# 1. 首次采样
result = monitor.evaluate()

assert result == {
    "status": "BASELINE",
    "window": None,
}, result

print("[TEST] FIRST_BASELINE= True")


# 2. 请求量不足：5 次请求，2 次错误
add_events(processed=3, errors=2)

result = monitor.evaluate()

assert result["status"] == "INSUFFICIENT_DATA"
assert result["window"]["window_requests"] == 5
assert result["window"]["window_error_rate"] == 40.0

print("[TEST] INSUFFICIENT_DATA= True")


# 3. 达到告警阈值：10 次请求，2 次错误
add_events(processed=8, errors=2)

result = monitor.evaluate()

assert result["status"] == "ALERT"
assert result["window"]["window_requests"] == 10
assert result["window"]["window_error_rate"] == 20.0

print("[TEST] ALERT_THRESHOLD= True")


# 4. 正常窗口：10 次请求，1 次错误
add_events(processed=9, errors=1)

result = monitor.evaluate()

assert result["status"] == "OK"
assert result["window"]["window_requests"] == 10
assert result["window"]["window_error_rate"] == 10.0

print("[TEST] NORMAL_WINDOW= True")


# 5. 没有新增请求
result = monitor.evaluate()

assert result["status"] == "INSUFFICIENT_DATA"
assert result["window"]["window_requests"] == 0

print("[TEST] ZERO_REQUESTS= True")


# 6. 模拟计数器重置
metrics.reset()

result = monitor.evaluate()

assert result == {
    "status": "RESET",
    "window": None,
}, result

print("[TEST] COUNTER_RESET= True")


# 7. 重置后重新计算
add_events(processed=7, errors=3)

result = monitor.evaluate()

assert result["status"] == "ALERT"
assert result["window"]["window_requests"] == 10
assert result["window"]["window_errors"] == 3
assert result["window"]["window_error_rate"] == 30.0

print("[TEST] AFTER_RESET_ALERT= True")

print("[TEST] ALL PASS: Webhook metrics monitor")
