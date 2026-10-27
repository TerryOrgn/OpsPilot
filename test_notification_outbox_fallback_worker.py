
from unittest.mock import patch

from notification_outbox_fallback_worker import (
    run_fallback_worker,
)


alerts = [
    {"ALERT_ID": 101, "CLAIM_TOKEN": "token-101"},
    {"ALERT_ID": 102, "CLAIM_TOKEN": "token-102"},
]


def fake_send(alert):
    if alert["ALERT_ID"] == 101:
        raise RuntimeError("Simulated delivery failure")


with (
    patch(
        "notification_outbox_fallback_worker."
        "claim_pending_fallback_alerts",
        return_value=alerts,
    ) as mock_claim,
    patch(
        "notification_outbox_fallback_worker."
        "confirm_fallback_alert_sent",
        return_value=True,
    ) as mock_sent,
    patch(
        "notification_outbox_fallback_worker."
        "confirm_fallback_alert_failed",
        return_value=True,
    ) as mock_failed,
):
    result = run_fallback_worker(
        send_alert=fake_send,
        limit=2,
    )

    assert result == {
        "claimed": 2,
        "sent": 1,
        "failed": 1,
        "confirmation_errors": 0,
    }

    mock_claim.assert_called_once_with(limit=2)

    mock_failed.assert_called_once_with(
        101, "token-101"
    )
    mock_sent.assert_called_once_with(
        102, "token-102"
    )

    print("[TEST] FAILED_ALERT_CONFIRMED= True")
    print("[TEST] SUCCESS_ALERT_CONFIRMED= True")
    print("[TEST] FAILURE_ISOLATION= True")
    print("[TEST] RESULT_COUNTS= True")
    print("[TEST] ALL PASS: Fallback worker mock")
