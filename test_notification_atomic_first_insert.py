
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from notification_monitor_state import (
    transition_dead_letter_state,
    get_dead_letter_state,
)

notification_type = "TEST_" + uuid4().hex[:20]

with ThreadPoolExecutor(max_workers=2) as executor:
    futures = [
        executor.submit(
            transition_dead_letter_state,
            notification_type,
            "ACTION_REQUIRED",
        )
        for _ in range(2)
    ]

    events = [future.result() for future in futures]

stored_status = get_dead_letter_state(notification_type)

print("[TEST] EVENTS=", events)
print("[TEST] STORED_STATUS=", stored_status)

assert events == [None, None]
assert stored_status == "ACTION_REQUIRED"

print("[TEST] ALL PASS: Concurrent first insert")
