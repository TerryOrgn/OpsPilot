
from webhook_metrics_analysis import (
    calculate_webhook_rates,
)


# 1. 正常计算
snapshot = {
    "processed_total": 80,
    "duplicate_total": 15,
    "conflict_total": 3,
    "error_total": 2,
}

result = calculate_webhook_rates(snapshot)

assert result == {
    "total_requests": 100,
    "duplicate_rate": 15.79,
    "error_rate": 2.0,
}, result

print("[TEST] NORMAL_RATES= True")


# 2. 零请求
empty = {
    "processed_total": 0,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 0,
}

result = calculate_webhook_rates(empty)

assert result["total_requests"] == 0
assert result["duplicate_rate"] == 0.0
assert result["error_rate"] == 0.0

print("[TEST] ZERO_REQUESTS= True")


# 3. 全部为重复请求
all_duplicate = {
    "processed_total": 0,
    "duplicate_total": 10,
    "conflict_total": 0,
    "error_total": 0,
}

result = calculate_webhook_rates(all_duplicate)

assert result["duplicate_rate"] == 100.0
assert result["error_rate"] == 0.0

print("[TEST] ALL_DUPLICATE= True")


# 4. 全部为错误请求
all_error = {
    "processed_total": 0,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 10,
}

result = calculate_webhook_rates(all_error)

assert result["duplicate_rate"] == 0.0
assert result["error_rate"] == 100.0

print("[TEST] ALL_ERROR= True")


# 5. 拒绝负数
invalid = {
    "processed_total": -1,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 0,
}

try:
    calculate_webhook_rates(invalid)
except ValueError:
    print("[TEST] NEGATIVE_VALUE_REJECTED= True")
else:
    raise AssertionError("Negative metric must be rejected")


# 6. 不修改原始快照
assert snapshot == {
    "processed_total": 80,
    "duplicate_total": 15,
    "conflict_total": 3,
    "error_total": 2,
}

print("[TEST] SNAPSHOT_UNCHANGED= True")
print("[TEST] ALL PASS: Webhook metrics analysis")
