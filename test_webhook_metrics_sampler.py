
from webhook_metrics import WebhookMetrics
from webhook_metrics_sampler import MetricsWindowSampler


# 使用独立计数器，避免污染全局指标
metrics = WebhookMetrics()
sampler = MetricsWindowSampler(metrics)


# 1. 第一次采样
result = sampler.sample()

assert result == {
    "status": "BASELINE",
    "window": None,
}

print("[TEST] FIRST_BASELINE= True")


# 2. 增加正常请求和错误请求
for _ in range(8):
    metrics.record("PROCESSED")

for _ in range(2):
    metrics.record("ERROR")

result = sampler.sample()

assert result == {
    "status": "OK",
    "window": {
        "window_requests": 10,
        "window_errors": 2,
        "window_error_rate": 20.0,
    },
}, result

print("[TEST] NORMAL_WINDOW= True")


# 3. 没有新增请求
result = sampler.sample()

assert result["status"] == "OK"
assert result["window"]["window_requests"] == 0
assert result["window"]["window_error_rate"] == 0.0

print("[TEST] NO_NEW_REQUESTS= True")


# 4. 再增加 5 个正常请求
for _ in range(5):
    metrics.record("PROCESSED")

result = sampler.sample()

assert result["status"] == "OK"
assert result["window"]["window_requests"] == 5
assert result["window"]["window_errors"] == 0
assert result["window"]["window_error_rate"] == 0.0

print("[TEST] CONTINUOUS_SAMPLING= True")


# 5. 模拟计数器重置
metrics.reset()

result = sampler.sample()

assert result == {
    "status": "RESET",
    "window": None,
}

print("[TEST] COUNTER_RESET= True")


# 6. 重置后恢复正常采样
metrics.record("ERROR")

result = sampler.sample()

assert result == {
    "status": "OK",
    "window": {
        "window_requests": 1,
        "window_errors": 1,
        "window_error_rate": 100.0,
    },
}, result

print("[TEST] SAMPLING_AFTER_RESET= True")

print("[TEST] ALL PASS: Webhook metrics sampler")
