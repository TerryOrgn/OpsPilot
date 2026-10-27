
from unittest.mock import patch

import notification_scheduler as scheduler


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
        return_value=2
    ),
    patch.object(
        scheduler,
        "transition_dead_letter_state",
        return_value="DEAD_LETTER_DETECTED"
    ) as mock_transition,
):
    result = scheduler.execute_notification_cycle(
        notification_type="CONSOLE_TEST_PERSIST",
        limit=1
    )

    mock_transition.assert_called_once_with(
        "CONSOLE_TEST_PERSIST",
        "ACTION_REQUIRED"
    )

assert result["cycle_status"] == "SUCCESS"
assert result["dead_letter_status"] == "ACTION_REQUIRED"
assert result["dead_letter_event"] == "DEAD_LETTER_DETECTED"
assert result["exhausted_count"] == 2
assert result["state_persistence_status"] == "SUCCESS"
assert result["backlog_status"] == "NORMAL"

print("[TEST] TRANSITION_CALL=PASS")
print("[TEST] DEAD_LETTER_EVENT=", result["dead_letter_event"])
print("[TEST] ALL PASS: Scheduler persistent state integration")
print("[TEST] PERSISTENCE_STATUS=", result["state_persistence_status"])
