
import math


def evaluate_error_rate(
    window: dict,
    min_requests: int = 10,
    error_threshold: float = 20.0,
) -> dict:

    if type(min_requests) is not int or min_requests <= 0:
        raise ValueError("Invalid min_requests")

    if (
        type(error_threshold) not in (int, float)
        or not math.isfinite(error_threshold)
        or not 0 <= error_threshold <= 100
    ):
        raise ValueError("Invalid error_threshold")

    requests = window["window_requests"]
    errors = window["window_errors"]
    rate = window["window_error_rate"]

    if (
        type(requests) is not int
        or type(errors) is not int
        or requests < 0
        or errors < 0
        or errors > requests
    ):
        raise ValueError("Invalid window counts")

    if (
        type(rate) not in (int, float)
        or not math.isfinite(rate)
        or not 0 <= rate <= 100
    ):
        raise ValueError("Invalid window error rate")

    # 防止调用方传入与计数不一致的错误率
    expected_rate = (
        round(errors / requests * 100, 2)
        if requests > 0
        else 0.0
    )

    if abs(rate - expected_rate) > 0.001:
        raise ValueError("Inconsistent window error rate")

    if requests < min_requests:
        status = "INSUFFICIENT_DATA"
    elif rate >= error_threshold:
        status = "ALERT"
    else:
        status = "OK"

    return {
        "status": status,
        "window_requests": requests,
        "window_errors": errors,
        "window_error_rate": rate,
    }
