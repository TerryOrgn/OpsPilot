
from unittest.mock import patch
import pymysql

import notification_monitor_state as state


calls = 0


def connection_failed(notification_type, new_status):
    global calls
    calls += 1

    raise pymysql.err.OperationalError(
        2003,
        "Can't connect to MySQL server"
    )


with patch.object(
    state,
    "_transition_dead_letter_state_once",
    side_effect=connection_failed
), patch.object(
    state.time,
    "sleep",
    return_value=None
) as mock_sleep:

    try:
        state.transition_dead_letter_state(
            "CONSOLE_TEST_RETRY",
            "ACTION_REQUIRED"
        )
    except pymysql.err.OperationalError as exc:
        assert exc.args[0] == 2003
        print("[TEST] ERROR_CODE=", exc.args[0])
    else:
        raise AssertionError(
            "Expected MySQL connection error"
        )

    mock_sleep.assert_not_called()

print("[TEST] ATTEMPTS=", calls)

assert calls == 1

print("[TEST] ALL PASS: Non-deadlock error propagation")
