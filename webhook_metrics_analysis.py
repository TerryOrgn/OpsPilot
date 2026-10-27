
def calculate_webhook_rates(snapshot: dict) -> dict:
    required = (
        "processed_total",
        "duplicate_total",
        "conflict_total",
        "error_total",
    )

    for key in required:
        value = snapshot[key]

        if type(value) is not int or value < 0:
            raise ValueError(
                f"Invalid metric: {key}={value}"
            )

    processed = snapshot["processed_total"]
    duplicate = snapshot["duplicate_total"]
    conflict = snapshot["conflict_total"]
    error = snapshot["error_total"]

    # 成功处理及重复请求的总量
    eligible = processed + duplicate

    # 四类已统计请求总量
    total = eligible + conflict + error

    duplicate_rate = (
        duplicate / eligible * 100
        if eligible > 0 else 0.0
    )

    error_rate = (
        error / total * 100
        if total > 0 else 0.0
    )

    return {
        "total_requests": total,
        "duplicate_rate": round(duplicate_rate, 2),
        "error_rate": round(error_rate, 2),
    }
