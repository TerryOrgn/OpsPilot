
from unittest.mock import patch

import notification_scheduler as scheduler
from notification_monitor_state import get_dead_letter_state

notification_type = "CONSOLE_TEST_RESTART"

# 上一步已建立 ACTION_REQUIRED 状态
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
        return_value=2
    ),
):
    # 不 Mock transition_dead_letter_state：
    # 使用真实 MySQL 状态转换
    result = scheduler.execute_notification_cycle(
        notification_type=notification_type,
        limit=1
    )

assert result["cycle_status"] == "SUCCESS"
assert result["exhausted_count"] == 2
assert result["dead_letter_status"] == "ACTION_REQUIRED"
assert result["state_persistence_status"] == "SUCCESS"
assert result["dead_letter_event"] is None
assert result["backlog_status"] == "NORMAL"

print("[TEST] STORED_STATUS=", get_dead_letter_state(notification_type))
print("[TEST] DEAD_LETTER_EVENT=", result["dead_letter_event"])
print("[TEST] PERSISTENCE_STATUS=", result["state_persistence_status"])
print("[TEST] ALL PASS: Scheduler real DB state integration")
