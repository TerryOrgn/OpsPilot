
import time
import threading
from unittest.mock import patch

from notification_outbox_monitor_scheduler import (
    start_outbox_monitor_scheduler,
)


lock = threading.Lock()
run_count = 0
active_count = 0
max_active_count = 0


def mock_monitor(notification_type):
    global run_count, active_count, max_active_count

    with lock:
        run_count += 1
        active_count += 1
        max_active_count = max(
            max_active_count,
            active_count
        )

    # 模拟监控任务耗时超过调度间隔
    time.sleep(1.5)

    with lock:
        active_count -= 1


scheduler = None

try:
    # 调度间隔1秒，模拟任务耗时1.5秒
    with patch(
        "notification_outbox_monitor_scheduler.execute_outbox_monitor",
        side_effect=mock_monitor
    ):
        scheduler = start_outbox_monitor_scheduler(
            notification_type="TEST",
            interval_seconds=1
        )

        assert scheduler.running is True
        print("[TEST] SCHEDULER_STARTED= True")

        # 等待调度器执行
        time.sleep(5)

        # 等待正在执行的任务结束并关闭调度器
        scheduler.shutdown(wait=True)
        scheduler = None

    with lock:
        observed_runs = run_count
        observed_max_active = max_active_count

    assert observed_runs >= 2, observed_runs
    print("[TEST] RUN_COUNT=", observed_runs)

    assert observed_max_active == 1, observed_max_active
    print("[TEST] MAX_CONCURRENT_RUNS=", observed_max_active)

    print("[TEST] NO_OVERLAPPING_EXECUTION= True")
    print("[TEST] SCHEDULER_SHUTDOWN= True")
    print("[TEST] ALL PASS: Outbox monitor scheduler")

finally:
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=True)
