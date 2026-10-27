
from notification_scheduler_stats import NotificationSchedulerStats


def main():
    stats = NotificationSchedulerStats()

    test_cases = [
        ("SUCCESS", 1, 0, 0),
        ("FAILED", 1, 1, 1),
        ("FAILED", 1, 2, 2),
        ("SUCCESS", 2, 2, 0),
    ]

    for index, (
        status,
        expected_success,
        expected_failure,
        expected_consecutive
    ) in enumerate(test_cases, start=1):

        stats.record_result(status)
        result = stats.snapshot()

        assert result["total_runs"] == index
        assert result["success_count"] == expected_success
        assert result["failure_count"] == expected_failure
        assert (
            result["consecutive_failures"]
            == expected_consecutive
        )

        print(
            f"[TEST] RUN={index} "
            f"STATUS={status} "
            f"SUCCESS={result['success_count']} "
            f"FAILED={result['failure_count']} "
            f"CONSECUTIVE={result['consecutive_failures']}"
        )

    final = stats.snapshot()

    assert final["last_run_time"] is not None
    assert final["last_success_time"] is not None
    assert final["last_error_time"] is not None

    print("[TEST] PASS: All counters correct")
    print("[TEST] PASS: All timestamps recorded")
    print("[TEST] ALL PASS")


if __name__ == "__main__":
    main()
