
from audit_backoff_policy import calculate_backoff


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def expect_invalid(name, **kwargs):
    try:
        calculate_backoff(**kwargs)
    except ValueError:
        check(name, True)
    else:
        raise AssertionError(
            f"{name}: expected ValueError"
        )


# 1. 基本指数增长
check(
    "FIRST_FAILURE_1_SECOND",
    calculate_backoff(1) == 1.0,
)

check(
    "SECOND_FAILURE_2_SECONDS",
    calculate_backoff(2) == 2.0,
)

check(
    "THIRD_FAILURE_4_SECONDS",
    calculate_backoff(3) == 4.0,
)

check(
    "FOURTH_FAILURE_8_SECONDS",
    calculate_backoff(4) == 8.0,
)

# 2. 最大等待时间限制
check(
    "MAX_DELAY_CAPPED",
    calculate_backoff(5) == 8.0,
)

check(
    "LARGE_FAILURE_COUNT_CAPPED",
    calculate_backoff(1000) == 8.0,
)

# 3. 自定义参数
check(
    "CUSTOM_BASE_DELAY",
    calculate_backoff(
        3,
        base_delay=0.5,
        max_delay=10,
    ) == 2.0,
)

check(
    "CUSTOM_MAX_DELAY",
    calculate_backoff(
        4,
        base_delay=1,
        max_delay=3,
    ) == 3.0,
)

# 4. 参数校验
expect_invalid(
    "ZERO_FAILURE_REJECTED",
    failure_count=0,
)

expect_invalid(
    "NEGATIVE_FAILURE_REJECTED",
    failure_count=-1,
)

expect_invalid(
    "BOOLEAN_FAILURE_REJECTED",
    failure_count=True,
)

expect_invalid(
    "ZERO_BASE_DELAY_REJECTED",
    failure_count=1,
    base_delay=0,
)

expect_invalid(
    "MAX_LESS_THAN_BASE_REJECTED",
    failure_count=1,
    base_delay=5,
    max_delay=2,
)

expect_invalid(
    "INFINITE_DELAY_REJECTED",
    failure_count=1,
    max_delay=float("inf"),
)

print("[TEST] ALL PASS: Audit Backoff Policy")
