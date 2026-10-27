
from notification_scheduler_stats import NotificationSchedulerStats


def main():
    stats = NotificationSchedulerStats()

    test_cases = [
        (None, 0, "HEALTHY"),
        ("FAILED", 1, "HEALTHY"),
        ("FAILED", 2, "HEALTHY"),
        ("FAILED", 3, "UNHEALTHY"),
        ("FAILED", 4, "UNHEALTHY"),
        ("SUCCESS", 0, "HEALTHY"),
    ]

    for index, (
        cycle_status,
        expected_failures,
        expected_health
    ) in enumerate(test_cases):

        if cycle_status is not None:
            stats.record_result(cycle_status)

        actual_failures = stats.consecutive_failures
        actual_health = stats.get_health_status()

        assert actual_failures == expected_failures, (
            f"STEP={index}: expected failures "
            f"{expected_failures}, got {actual_failures}"
        )

        assert actual_health == expected_health, (
            f"STEP={index}: expected health "
            f"{expected_health}, got {actual_health}"
        )

        print(
            f"[TEST] STEP={index} "
            f"STATUS={cycle_status or 'INITIAL'} "
            f"CONSECUTIVE={actual_failures} "
            f"HEALTH={actual_health}"
        )

    print("[TEST] PASS: Health threshold = 3")
    print("[TEST] PASS: Recovery to HEALTHY")
    print("[TEST] ALL PASS")


if __name__ == "__main__":
    main()
