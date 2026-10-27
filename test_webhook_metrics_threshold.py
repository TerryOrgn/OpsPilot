
from webhook_metrics_threshold import evaluate_error_rate


def check(name, window, expected_status):
    result = evaluate_error_rate(window)

    assert result["status"] == expected_status, result
    print(f"[TEST] {name}= True")


# 1. 请求量不足，即使错误率很高也不告警
check(
    "INSUFFICIENT_DATA",
    {
        "window_requests": 5,
        "window_errors": 5,
        "window_error_rate": 100.0,
    },
    "INSUFFICIENT_DATA",
)

# 2. 正好达到阈值
check(
    "THRESHOLD_BOUNDARY",
    {
        "window_requests": 10,
        "window_errors": 2,
        "window_error_rate": 20.0,
    },
    "ALERT",
)

# 3. 错误率低于阈值
check(
    "NORMAL_RATE",
    {
        "window_requests": 20,
        "window_errors": 2,
        "window_error_rate": 10.0,
    },
    "OK",
)

# 4. 零请求
check(
    "ZERO_REQUESTS",
    {
        "window_requests": 0,
        "window_errors": 0,
        "window_error_rate": 0.0,
    },
    "INSUFFICIENT_DATA",
)

# 5. 全部请求失败
check(
    "ALL_ERRORS",
    {
        "window_requests": 10,
        "window_errors": 10,
        "window_error_rate": 100.0,
    },
    "ALERT",
)

# 6. 不一致的错误率必须拒绝
try:
    evaluate_error_rate({
        "window_requests": 10,
        "window_errors": 2,
        "window_error_rate": 50.0,
    })
except ValueError:
    print("[TEST] INCONSISTENT_RATE_REJECTED= True")
else:
    raise AssertionError("Inconsistent rate must be rejected")


# 7. 非法阈值必须拒绝
try:
    evaluate_error_rate(
        {
            "window_requests": 10,
            "window_errors": 2,
            "window_error_rate": 20.0,
        },
        error_threshold=float("nan"),
    )
except ValueError:
    print("[TEST] INVALID_THRESHOLD_REJECTED= True")
else:
    raise AssertionError("Invalid threshold must be rejected")


print("[TEST] ALL PASS: Webhook metrics threshold")
