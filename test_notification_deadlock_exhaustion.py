
from unittest.mock import patch
import pymysql

import notification_monitor_state as state


calls = 0


def always_deadlock(notification_type, new_status):
    global calls
    calls += 1

    raise pymysql.err.OperationalError(
        1213,
        "Deadlock found when trying to get lock"
    )


with patch.object(
    state,
    "_transition_dead_letter_state_once",
    side_effect=always_deadlock
), patch.object(
    state.time,
    "sleep",
    return_value=None
):
    try:
        state.transition_dead_letter_state(
            "CONSOLE_TEST_RETRY",
            "ACTION_REQUIRED"
        )
    except pymysql.err.OperationalError as exc:
        assert exc.args[0] == 1213
        print("[TEST] ERROR_CODE=", exc.args[0])
    else:
        raise AssertionError(
            "Expected deadlock exception after max retries"
        )

print("[TEST] ATTEMPTS=", calls)

assert calls == 3

print("[TEST] ALL PASS: Deadlock retry exhaustion")
