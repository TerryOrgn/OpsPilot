
from unittest.mock import patch

from notification_scheduler import (
    execute_notification_cycle,
    notification_stats
)


def main():
    test_cases = [
        {"cycle_status": "SUCCESS"},
        {"cycle_status": "FAILED"},
        RuntimeError("Simulated database connection failure"),
        {"cycle_status": "SUCCESS"}
    ]

    expected_consecutive = [0, 1, 2, 0]

    for index, simulated_result in enumerate(test_cases, start=1):

        if isinstance(simulated_result, Exception):
            mock_config = {
                "side_effect": simulated_result
            }
        else:
            mock_config = {
                "return_value": simulated_result
            }

        with patch(
            "notification_scheduler.run_notification_cycle",
            **mock_config
        ):
            result = execute_notification_cycle(
                notification_type="CONSOLE_TEST_CYCLE",
                limit=1
            )

        snapshot = notification_stats.snapshot()

        expected_status = (
            "FAILED"
            if isinstance(simulated_result, Exception)
            else simulated_result["cycle_status"]
        )

        assert result["cycle_status"] == expected_status
        assert snapshot["total_runs"] == index
        assert (
            snapshot["consecutive_failures"]
            == expected_consecutive[index - 1]
        )

        print(
            f"[TEST] RUN={index} "
            f"STATUS={result['cycle_status']} "
            f"TOTAL={snapshot['total_runs']} "
            f"CONSECUTIVE={snapshot['consecutive_failures']}"
        )

    final = notification_stats.snapshot()

    assert final["success_count"] == 2
    assert final["failure_count"] == 2
    assert final["consecutive_failures"] == 0
    assert final["last_run_time"] is not None
    assert final["last_success_time"] is not None
    assert final["last_error_time"] is not None

    print("[TEST] PASS: All scheduler statistics correct")
    print("[TEST] PASS: Exception recorded as FAILED")
    print("[TEST] ALL PASS")


if __name__ == "__main__":
    main()
