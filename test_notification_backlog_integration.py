
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import notification_scheduler
from notification_scheduler_stats import NotificationSchedulerStats


def main():
    notification_scheduler.notification_stats = (
        NotificationSchedulerStats()
    )

    mock_cycle_result = {
        "cycle_status": "SUCCESS"
    }

    mock_backlog = {
        "pending": 7,
        "failed": 5,
        "total": 12
    }

    with (
        patch(
            "notification_scheduler.run_notification_cycle",
            return_value=mock_cycle_result
        ),
        patch(
            "notification_scheduler.get_notification_backlog",
            return_value=mock_backlog
        )
    ):
        output_buffer = io.StringIO()

        with redirect_stdout(output_buffer):
            result = notification_scheduler.execute_notification_cycle(
                notification_type="CONSOLE_TEST_CYCLE",
                limit=1
            )

    output = output_buffer.getvalue()
    print(output, end="")

    assert result["cycle_status"] == "SUCCESS"


    assert result["backlog_status"] == "BACKLOG_WARNING", (
        f"Expected BACKLOG_WARNING, "
        f"got {result['backlog_status']}"
    )


    assert (
        "[NOTIFICATION-BACKLOG] "
        "TYPE=CONSOLE_TEST_CYCLE "
        "PENDING=7 FAILED=5 TOTAL=12 "
        "STATUS=BACKLOG_WARNING"
    ) in output

    print("[TEST] ALL PASS: Backlog warning integration")


if __name__ == "__main__":
    main()
