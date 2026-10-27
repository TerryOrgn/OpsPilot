
from unittest.mock import patch

import notification_scheduler as scheduler
from notification_backlog import DeadLetterStateTracker, get_notification_backlog, get_exhausted_notification_count

counts = iter([0, 2, 2, 0, 0])

# 每次测试使用独立 Tracker，避免其他测试影响
with patch.object(
    scheduler,
    "dead_letter_trackers",
        {}
), patch.object(
    scheduler,
    "run_notification_cycle",
    return_value={"cycle_status": "SUCCESS"}
), patch.object(
    scheduler,
    "get_notification_backlog",
    return_value={"pending": 0, "failed": 0, "total": 0}
), patch.object(
    scheduler,
    "get_exhausted_notification_count",
    side_effect=lambda notification_type: next(counts)
):
    events = []

    for _ in range(5):
        result = scheduler.execute_notification_cycle(
            notification_type="CONSOLE_TEST_CYCLE",
            limit=1
        )
        events.append(result["dead_letter_event"])

expected = [
    None,
    "DEAD_LETTER_DETECTED",
    None,
    "DEAD_LETTER_CLEARED",
    None,
]

assert events == expected, (
    f"Expected {expected}, got {events}"
)

print("[TEST] EVENTS=", events)
print("[TEST] ALL PASS: Dead-letter transition integration")
