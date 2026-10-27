
def calculate_backoff(
    failure_count,
    base_delay=1.0,
    max_delay=8.0,
):
    """
    根据连续失败次数计算下一次重试等待时间。

    仅计算时间，不执行 sleep。
    """

    if (
        isinstance(failure_count, bool)
        or not isinstance(failure_count, int)
        or failure_count < 1
    ):
        raise ValueError(
            "failure_count must be a positive integer"
        )

    for name, value in (
        ("base_delay", base_delay),
        ("max_delay", max_delay),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not (0 < value < float("inf"))
        ):
            raise ValueError(
                f"{name} must be a finite positive number"
            )

    if max_delay < base_delay:
        raise ValueError(
            "max_delay must be >= base_delay"
        )

    # 避免极大 failure_count 导致指数计算溢出
    delay = float(base_delay)

    for _ in range(failure_count - 1):
        if delay >= max_delay:
            break
        delay = min(delay * 2, max_delay)

    return min(delay, max_delay)
