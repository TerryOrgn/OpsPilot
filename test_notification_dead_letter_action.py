
from unittest.mock import patch

from notification_scheduler import execute_notification_cycle


with patch(
    "notification_scheduler.run_notification_cycle",
    return_value={"cycle_status": "SUCCESS"}
), patch(
    "notification_scheduler.get_notification_backlog",
    return_value={"pending": 0, "failed": 0, "total": 0}
), patch(
    "notification_scheduler.get_exhausted_notification_count",
    return_value=2
):
    result = execute_notification_cycle(
        notification_type="CONSOLE_TEST_CYCLE",
        limit=1
    )

assert result["cycle_status"] == "SUCCESS"
assert result["backlog_status"] == "NORMAL"
assert result["exhausted_count"] == 2
assert result["dead_letter_status"] == "ACTION_REQUIRED"

print("[TEST] ALL PASS: Dead-letter action required")
