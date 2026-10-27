
from unittest.mock import patch

import notification_scheduler as scheduler
from notification_monitor_state import get_dead_letter_state

notification_type = "CONSOLE_TEST_RESTART"

assert get_dead_letter_state(notification_type) == "ACTION_REQUIRED"

with (
    patch.object(
        scheduler,
        "run_notification_cycle",
        return_value={"cycle_status": "SUCCESS"}
    ),
    patch.object(
        scheduler,
        "get_notification_backlog",
        return_value={"pending": 0, "failed": 0, "total": 0}
    ),
    patch.object(
        scheduler,
        "get_exhausted_notification_count",
        return_value=0
    ),
):
    result = scheduler.execute_notification_cycle(
        notification_type=notification_type,
        limit=1
    )

assert result["cycle_status"] == "SUCCESS"
assert result["exhausted_count"] == 0
assert result["dead_letter_status"] == "NORMAL"
assert result["state_persistence_status"] == "SUCCESS"
assert result["dead_letter_event"] == "DEAD_LETTER_CLEARED"

stored_status = get_dead_letter_state(notification_type)
assert stored_status == "NORMAL"

print("[TEST] DEAD_LETTER_EVENT=", result["dead_letter_event"])
print("[TEST] STORED_STATUS=", stored_status)
print("[TEST] ALL PASS: Scheduler dead letter recovery")
