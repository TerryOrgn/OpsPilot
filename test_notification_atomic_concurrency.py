
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from notification_monitor_state import (
    transition_dead_letter_state,
)

notification_type = "TEST_" + uuid4().hex[:20]

# 首先建立 NORMAL 基线
initial = transition_dead_letter_state(
    notification_type, "NORMAL"
)
assert initial is None

# 让两个线程同时尝试触发死信事件
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

print("[TEST] EVENTS=", events)

assert events.count("DEAD_LETTER_DETECTED") == 1
assert events.count(None) == 1

print("[TEST] ALL PASS: Concurrent transition deduplication")
