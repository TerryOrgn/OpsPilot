
METRIC_KEYS = (
    "processed_total",
    "duplicate_total",
    "conflict_total",
    "error_total",
)


def calculate_window_error_rate(
    previous: dict,
    current: dict,
) -> dict:

    delta = {}

    for key in METRIC_KEYS:
        old = previous[key]
        new = current[key]

        if (
            type(old) is not int
            or type(new) is not int
            or old < 0
            or new < 0
        ):
            raise ValueError(
                f"Invalid metric value: {key}"
            )

        if new < old:
            raise ValueError(
                f"Counter decreased: {key}"
            )

        delta[key] = new - old

    total_requests = sum(delta.values())
    error_requests = delta["error_total"]

    error_rate = (
        error_requests / total_requests * 100
        if total_requests > 0
        else 0.0
    )

    return {
        "window_requests": total_requests,
        "window_errors": error_requests,
        "window_error_rate": round(
            error_rate,
            2,
        ),
    }
