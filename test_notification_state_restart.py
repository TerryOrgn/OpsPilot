
import sys

from notification_monitor_state import (
    transition_dead_letter_state,
    get_dead_letter_state,
)

notification_type = "CONSOLE_TEST_RESTART"

if len(sys.argv) != 2 or sys.argv[1] not in ("init", "check"):
    raise SystemExit("Usage: python test_notification_state_restart.py init|check")

mode = sys.argv[1]

if mode == "init":
    # 建立 NORMAL 基线，再转换为 ACTION_REQUIRED
    first = transition_dead_letter_state(notification_type, "NORMAL")
    assert first is None

    event = transition_dead_letter_state(
        notification_type,
        "ACTION_REQUIRED"
    )
    assert event == "DEAD_LETTER_DETECTED"

    print("[TEST] INITIAL_EVENT=", event)

else:
    # 新 Python 进程读取之前保存的状态
    event = transition_dead_letter_state(
        notification_type,
        "ACTION_REQUIRED"
    )

    stored_status = get_dead_letter_state(notification_type)

    assert event is None
    assert stored_status == "ACTION_REQUIRED"

    print("[TEST] RESTART_EVENT=", event)
    print("[TEST] STORED_STATUS=", stored_status)
    print("[TEST] ALL PASS: Cross-process state persistence")
