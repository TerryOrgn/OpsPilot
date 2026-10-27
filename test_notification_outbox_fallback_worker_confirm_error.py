
from unittest.mock import patch

from notification_outbox_fallback_worker import (
    run_fallback_worker,
)


alerts = [
    {"ALERT_ID": 201, "CLAIM_TOKEN": "token-201"},
    {"ALERT_ID": 202, "CLAIM_TOKEN": "token-202"},
]

delivered = []


def fake_send(alert):
    delivered.append(alert["ALERT_ID"])


def fake_confirm_sent(alert_id, claim_token):
    if alert_id == 201:
        raise RuntimeError("Simulated MySQL failure")
    return True


with (
    patch(
        "notification_outbox_fallback_worker."
        "claim_pending_fallback_alerts",
        return_value=alerts,
    ),
    patch(
        "notification_outbox_fallback_worker."
        "confirm_fallback_alert_sent",
        side_effect=fake_confirm_sent,
    ) as mock_sent,
    patch(
        "notification_outbox_fallback_worker."
        "confirm_fallback_alert_failed",
    ) as mock_failed,
):
    result = run_fallback_worker(
        send_alert=fake_send,
        limit=2,
    )

    assert delivered == [201, 202]
    print("[TEST] BOTH_ALERTS_DELIVERED= True")

    assert result == {
        "claimed": 2,
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 1,
    }
    print("[TEST] CONFIRM_ERROR_COUNTED= True")

    assert mock_sent.call_count == 2
    mock_failed.assert_not_called()
    print("[TEST] NO_FALSE_FAILURE_CONFIRM= True")

    print("[TEST] CONFIRM_ERROR_ISOLATED= True")
    print("[TEST] ALL PASS: Fallback worker confirm error")
