
from unittest.mock import patch

from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
)


with (
    patch(
        "notification_outbox_fallback_scheduler."
        "recover_stale_fallback_alerts",
        side_effect=RuntimeError("Simulated MySQL failure"),
    ) as mock_recover,
    patch(
        "notification_outbox_fallback_scheduler."
        "requeue_due_failed_fallback_alerts",
    ) as mock_requeue,
    patch(
        "notification_outbox_fallback_scheduler."
        "run_fallback_worker",
    ) as mock_worker,
):
    try:
        run_fallback_cycle()
    except RuntimeError as exc:
        assert str(exc) == "Simulated MySQL failure"
        print("[TEST] EXCEPTION_PROPAGATED= True")
    else:
        raise AssertionError("Expected RuntimeError")

    mock_recover.assert_called_once()
    mock_requeue.assert_not_called()
    mock_worker.assert_not_called()

    print("[TEST] DOWNSTREAM_STEPS_SKIPPED= True")


print("[TEST] ALL PASS: Fallback scheduler error")
