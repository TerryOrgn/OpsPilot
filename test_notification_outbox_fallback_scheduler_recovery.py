
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler

from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
)


attempts = []
completed = threading.Event()


def mock_recover():
    attempts.append("recover")

    if len(attempts) == 1:
        raise RuntimeError("Simulated temporary DB failure")

    return 0


def mock_requeue():
    return 0


def mock_worker(send_alert, limit):
    attempts.append("worker")
    completed.set()

    return {
        "claimed": 0,
        "sent": 0,
        "failed": 0,
        "confirmation_errors": 0,
    }


scheduler = BackgroundScheduler()

try:
    with (
        patch(
            "notification_outbox_fallback_scheduler."
            "recover_stale_fallback_alerts",
            side_effect=mock_recover,
        ),
        patch(
            "notification_outbox_fallback_scheduler."
            "requeue_due_failed_fallback_alerts",
            side_effect=mock_requeue,
        ),
        patch(
            "notification_outbox_fallback_scheduler."
            "run_fallback_worker",
            side_effect=mock_worker,
        ),
    ):
        # 测试专用：1 秒间隔，不修改生产配置
        scheduler.add_job(
            run_fallback_cycle,
            trigger="interval",
            seconds=1,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(
                milliseconds=100
            ),
        )

        scheduler.start()

        assert completed.wait(timeout=5), (
            "Scheduler did not recover within 5 seconds"
        )

        assert attempts == [
            "recover",
            "recover",
            "worker",
        ]

        print("[TEST] FIRST_CYCLE_FAILED= True")
        print("[TEST] SECOND_CYCLE_SUCCEEDED= True")
        print("[TEST] SCHEDULER_CONTINUED= True")

    print("[TEST] ALL PASS: Fallback scheduler recovery")

finally:
    if scheduler.running:
        scheduler.shutdown(wait=True)
