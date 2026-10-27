
import io
from contextlib import redirect_stdout
from unittest.mock import patch

import notification_scheduler
from notification_scheduler_stats import NotificationSchedulerStats


def main():
    notification_scheduler.notification_stats = (
        NotificationSchedulerStats()
    )

    with (
        patch(
            "notification_scheduler.run_notification_cycle",
            return_value={"cycle_status": "SUCCESS"}
        ),
        patch(
            "notification_scheduler.get_notification_backlog",
            side_effect=RuntimeError("Simulated backlog DB failure")
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


    assert result["backlog_status"] == "UNKNOWN", (
        f"Expected UNKNOWN, got {result['backlog_status']}"
    )



    assert (
        "[NOTIFICATION-BACKLOG] CHECK_FAILED "
        "STATUS=UNKNOWN "
        "TYPE=RuntimeError "
        "MESSAGE=Simulated backlog DB failure"
    ) in output


    assert "STATUS=NORMAL" not in output
    assert "STATUS=BACKLOG_WARNING" not in output

    print("[TEST] ALL PASS: Backlog query failure handling")


if __name__ == "__main__":
    main()
