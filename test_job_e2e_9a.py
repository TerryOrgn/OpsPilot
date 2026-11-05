
import os
import threading
from unittest.mock import patch

from monitor_lock import run_with_monitor_lock

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

import scheduler as scheduler_module


def main():
    status = scheduler_module.monitor_status

    status.update({
        "last_run_time": None,
        "last_success_time": None,
        "last_error_time": None,
        "last_error_message": None,
        "total_runs": 0,
        "success_count": 0,
        "failure_count": 0,
        "consecutive_failures": 0,
    })

    scheduler = BlockingScheduler()
    trigger_count = 0
    completed = threading.Event()

    def fake_lock(monitor_func):
        assert monitor_func is scheduler_module.monitor_jobs
        return True

    def on_event(event):
        nonlocal trigger_count

        scheduler_module.on_job_event(event)

        if event.code == EVENT_JOB_EXECUTED:
            trigger_count += 1

            if trigger_count >= 3:
                completed.set()

    scheduler.add_job(
        func=scheduler_module.scheduled_monitor,
        trigger="interval",
        seconds=2,
        id="opspilot_job_monitor_test",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1,
    )

    scheduler.add_listener(
        on_event,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
    )

    # 最多等待 12 秒，避免测试无限运行
    def stop_scheduler():
        completed.wait(timeout=12)

        if scheduler.running:
            scheduler.shutdown(wait=True)

    stopper = threading.Thread(
        target=stop_scheduler,
        daemon=True,
    )
    stopper.start()

    try:
        with patch.object(
            scheduler_module,
            "run_with_monitor_lock",
            side_effect=fake_lock,
        ):
            scheduler.start()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)

    assert completed.is_set(), (
        f"12秒内未完成3次调度，实际 {trigger_count} 次"
    )

    assert trigger_count == 3, (
        f"预期3次触发，实际 {trigger_count} 次"
    )

    assert status["total_runs"] == 3
    assert status["success_count"] == 3
    assert status["failure_count"] == 0

    print("[TEST] APSCHEDULER_TRIGGER_COUNT=PASS")
    print("[TEST] SCHEDULER_STATISTICS=PASS")
    print("[TEST] ALL PASS: JOB-E2E-9A")


if __name__ == "__main__":
    main()
