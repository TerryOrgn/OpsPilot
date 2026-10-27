
from unittest.mock import patch
import pymysql

import notification_monitor_state as state


calls = 0


def fake_transition(notification_type, new_status):
    global calls
    calls += 1

    if calls < 3:
        raise pymysql.err.OperationalError(
            1213,
            "Deadlock found when trying to get lock"
        )

    return "DEAD_LETTER_DETECTED"


with patch.object(
    state,
    "_transition_dead_letter_state_once",
    side_effect=fake_transition
), patch.object(
    state.time,
    "sleep",
    return_value=None
):
    event = state.transition_dead_letter_state(
        "CONSOLE_TEST_RETRY",
        "ACTION_REQUIRED"
    )

print("[TEST] ATTEMPTS=", calls)
print("[TEST] EVENT=", event)

assert calls == 3
assert event == "DEAD_LETTER_DETECTED"

print("[TEST] ALL PASS: Deadlock retry")
