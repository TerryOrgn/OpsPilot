
from webhook_metrics_window import (
    calculate_window_error_rate,
)


# 1. 正常窗口计算
previous = {
    "processed_total": 80,
    "duplicate_total": 15,
    "conflict_total": 3,
    "error_total": 2,
}

current = {
    "processed_total": 120,
    "duplicate_total": 20,
    "conflict_total": 3,
    "error_total": 7,
}

result = calculate_window_error_rate(
    previous,
    current,
)

assert result == {
    "window_requests": 50,
    "window_errors": 5,
    "window_error_rate": 10.0,
}, result

print("[TEST] NORMAL_WINDOW_RATE= True")


# 2. 没有新增请求
result = calculate_window_error_rate(
    current,
    current,
)

assert result == {
    "window_requests": 0,
    "window_errors": 0,
    "window_error_rate": 0.0,
}

print("[TEST] ZERO_WINDOW_REQUESTS= True")


# 3. 全部新增请求均失败
all_error_previous = {
    "processed_total": 0,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 0,
}

all_error_current = {
    "processed_total": 0,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 10,
}

result = calculate_window_error_rate(
    all_error_previous,
    all_error_current,
)

assert result["window_error_rate"] == 100.0

print("[TEST] ALL_ERRORS= True")


# 4. 计数器减少必须拒绝
decreased = {
    "processed_total": 79,
    "duplicate_total": 15,
    "conflict_total": 3,
    "error_total": 2,
}

try:
    calculate_window_error_rate(
        previous,
        decreased,
    )
except ValueError:
    print("[TEST] COUNTER_DECREASE_REJECTED= True")
else:
    raise AssertionError(
        "Counter decrease must be rejected"
    )


# 5. 非法负数必须拒绝
invalid = {
    "processed_total": -1,
    "duplicate_total": 0,
    "conflict_total": 0,
    "error_total": 0,
}

try:
    calculate_window_error_rate(
        invalid,
        current,
    )
except ValueError:
    print("[TEST] NEGATIVE_VALUE_REJECTED= True")
else:
    raise AssertionError(
        "Negative metric must be rejected"
    )


# 6. 原始快照不能被修改
assert previous == {
    "processed_total": 80,
    "duplicate_total": 15,
    "conflict_total": 3,
    "error_total": 2,
}

assert current == {
    "processed_total": 120,
    "duplicate_total": 20,
    "conflict_total": 3,
    "error_total": 7,
}

print("[TEST] SNAPSHOTS_UNCHANGED= True")

print("[TEST] ALL PASS: Webhook window error rate")
