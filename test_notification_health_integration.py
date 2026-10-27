
from unittest.mock import patch

import notification_scheduler
from notification_scheduler_stats import NotificationSchedulerStats

import io
from contextlib import redirect_stdout

def main():
    # 每次测试从全新的统计状态开始
    notification_scheduler.notification_stats = (
        NotificationSchedulerStats()
    )

    # 模拟三次执行异常，随后一次成功

    outcomes = [
        RuntimeError("Simulated DB failure 1"),
        RuntimeError("Simulated DB failure 2"),
        RuntimeError("Simulated DB failure 3"),
        RuntimeError("Simulated DB failure 4"),
        RuntimeError("Simulated DB failure 5"),
        {"cycle_status": "SUCCESS"},
    ]


    expected = [
        ("FAILED", 1, "HEALTHY"),
        ("FAILED", 2, "HEALTHY"),
        ("FAILED", 3, "UNHEALTHY"),
        ("FAILED", 4, "UNHEALTHY"),
        ("FAILED", 5, "UNHEALTHY"),
        ("SUCCESS", 0, "HEALTHY"),
    ]

    with patch(
        "notification_scheduler.run_notification_cycle",
        side_effect=outcomes
    ):
        for index, (
            expected_status,
            expected_failures,
            expected_health
        ) in enumerate(expected, start=1):


            output_buffer = io.StringIO()

            with redirect_stdout(output_buffer):
                result = notification_scheduler.execute_notification_cycle(
                    notification_type="CONSOLE_TEST_CYCLE",
                    limit=1
                )

            output = output_buffer.getvalue()
            print(output, end="")

            degraded_count = output.count(
                "EVENT=HEALTH_DEGRADED"
            )
            recovered_count = output.count(
                "EVENT=HEALTH_RECOVERED"
            )

            expected_degraded = 1 if index == 3 else 0
            expected_recovered = 1 if index == 6 else 0

            assert degraded_count == expected_degraded, (
                f"STEP={index}: unexpected degraded events"
            )

            assert recovered_count == expected_recovered, (
                f"STEP={index}: unexpected recovered events"
            )


            stats = notification_scheduler.notification_stats

            assert result["cycle_status"] == expected_status
            assert stats.consecutive_failures == expected_failures
            assert stats.get_health_status() == expected_health

            print(
                f"[TEST] STEP={index} "
                f"CYCLE={result['cycle_status']} "
                f"CONSECUTIVE={stats.consecutive_failures} "
                f"HEALTH={stats.get_health_status()}"
            )

    print("[TEST] ALL PASS")


if __name__ == "__main__":
    main()
