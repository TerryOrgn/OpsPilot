
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
        side_effect=RuntimeError("Simulated state DB failure")
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

# 死信数量查询已经成功，必须保留结果
assert result["exhausted_count"] == 2
assert result["dead_letter_status"] == "ACTION_REQUIRED"

# 持久化失败应独立标记
assert result["state_persistence_status"] == "FAILED"
assert result["dead_letter_event"] is None

# 不影响其他监控结果
assert result["backlog_status"] == "NORMAL"

print("[TEST] CYCLE_STATUS=", result["cycle_status"])
print("[TEST] EXHAUSTED_COUNT=", result["exhausted_count"])
print("[TEST] DEAD_LETTER_STATUS=", result["dead_letter_status"])
print("[TEST] PERSISTENCE_STATUS=", result["state_persistence_status"])
print("[TEST] DEAD_LETTER_EVENT=", result["dead_letter_event"])
print("[TEST] BACKLOG_STATUS=", result["backlog_status"])

print("[TEST] ALL PASS: Persistence failure isolation")
