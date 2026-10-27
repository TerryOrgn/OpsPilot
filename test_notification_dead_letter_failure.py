
from unittest.mock import patch

from notification_scheduler import execute_notification_cycle


def fake_cycle(notification_type, limit):
    return {"cycle_status": "SUCCESS"}


def fake_backlog(notification_type):
    return {"pending": 0, "failed": 0, "total": 0}


with patch(
    "notification_scheduler.run_notification_cycle",
    side_effect=fake_cycle
), patch(
    "notification_scheduler.get_notification_backlog",
    side_effect=fake_backlog
), patch(
    "notification_scheduler.get_exhausted_notification_count",
    side_effect=RuntimeError("Simulated dead-letter DB failure")
):
    result = execute_notification_cycle(
        notification_type="CONSOLE_TEST_CYCLE",
        limit=1
    )

assert result["cycle_status"] == "SUCCESS"
assert result["backlog_status"] == "NORMAL"
assert result["exhausted_count"] is None
assert result["dead_letter_status"] == "UNKNOWN", (
    f"Expected UNKNOWN, got {result['dead_letter_status']}"
)

print("[TEST] ALL PASS: Dead-letter failure isolation")
