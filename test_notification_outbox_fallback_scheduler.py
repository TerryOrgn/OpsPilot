
from unittest.mock import patch

from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
    create_fallback_scheduler,
)


calls = []


def mock_recover():
    calls.append("recover")
    return 2


def mock_requeue():
    calls.append("requeue")
    return 1


def mock_worker(send_alert, limit):
    calls.append("worker")
    assert callable(send_alert)
    assert limit == 10
    return {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 0,
    }


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
    result = run_fallback_cycle()

assert calls == ["recover", "requeue", "worker"]
print("[TEST] EXECUTION_ORDER_VALID= True")

assert result["sent"] == 1
print("[TEST] CYCLE_RESULT_VALID= True")


scheduler = create_fallback_scheduler()

try:
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1

    job = jobs[0]
    assert job.id == "fallback_worker"
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == 30

    assert job.trigger.interval.total_seconds() == 60

    print("[TEST] SCHEDULER_CONFIG_VALID= True")

finally:
    scheduler.shutdown(wait=False) if scheduler.running else None


print("[TEST] ALL PASS: Fallback scheduler")
