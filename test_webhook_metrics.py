
from concurrent.futures import ThreadPoolExecutor

from webhook_metrics import WebhookMetrics


metrics = WebhookMetrics()

# 1. 验证四种结果的计数
metrics.record("PROCESSED")
metrics.record("PROCESSED")
metrics.record("DUPLICATE")
metrics.record("CONFLICT")
metrics.record("ERROR")

result = metrics.snapshot()

assert result == {
    "processed_total": 2,
    "duplicate_total": 1,
    "conflict_total": 1,
    "error_total": 1,
}, result

print("[TEST] BASIC_COUNTERS= True")


# 2. 验证 snapshot 不会暴露内部字典
snapshot = metrics.snapshot()
snapshot["processed_total"] = 999

assert metrics.snapshot()["processed_total"] == 2

print("[TEST] SNAPSHOT_ISOLATION= True")


# 3. 验证多线程计数
metrics.reset()

def record_processed(_):
    metrics.record("PROCESSED")


with ThreadPoolExecutor(max_workers=10) as executor:
    list(executor.map(record_processed, range(1000)))

assert metrics.snapshot()["processed_total"] == 1000

print("[TEST] CONCURRENT_COUNTER= True")


# 4. 验证非法结果被拒绝
try:
    metrics.record("UNKNOWN")
except ValueError:
    print("[TEST] UNKNOWN_RESULT_REJECTED= True")
else:
    raise AssertionError("UNKNOWN result must be rejected")


# 5. 验证 reset
metrics.reset()

assert all(
    value == 0
    for value in metrics.snapshot().values()
)

print("[TEST] RESET= True")
print("[TEST] ALL PASS: Webhook metrics")
