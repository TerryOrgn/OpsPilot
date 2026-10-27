
from unittest.mock import patch

import notification_scheduler as scheduler


counts = {
    "CONSOLE": iter([0, 0, 0]),
    "EMAIL": iter([0, 2, 2]),
}


def fake_exhausted_count(notification_type):
    return next(counts[notification_type])


with patch.object(
    scheduler, "dead_letter_trackers", {}
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
    side_effect=fake_exhausted_count
):
    events = []

    for notification_type in [
        "CONSOLE",
        "EMAIL",
        "EMAIL",
        "CONSOLE",
        "EMAIL",
        "CONSOLE",
    ]:
        result = scheduler.execute_notification_cycle(
            notification_type=notification_type,
            limit=1
        )
        events.append(
            (notification_type, result["dead_letter_event"])
        )


expected = [
    ("CONSOLE", None),
    ("EMAIL", None),
    ("EMAIL", "DEAD_LETTER_DETECTED"),
    ("CONSOLE", None),
    ("EMAIL", None),
    ("CONSOLE", None),
]

assert events == expected, (
    f"Expected {expected}, got {events}"
)

print("[TEST] EVENTS=", events)
print("[TEST] ALL PASS: Multi-type dead-letter isolation")
