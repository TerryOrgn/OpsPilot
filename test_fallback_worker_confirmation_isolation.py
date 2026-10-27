from unittest.mock import patch
from urllib.error import HTTPError

import notification_outbox_fallback_worker as worker


alerts = [
    {"ALERT_ID": 101, "CLAIM_TOKEN": "token-101"},
    {"ALERT_ID": 102, "CLAIM_TOKEN": "token-102"},
]

processed = []


def mock_send(alert):
    processed.append(alert["ALERT_ID"])

    raise HTTPError(
        url="http://127.0.0.1/webhook",
        code=409 if alert["ALERT_ID"] == 101 else 500,
        msg="Simulated HTTP error",
        hdrs={},
        fp=None,
    )


def mock_confirm_conflict(alert_id, claim_token):
    raise RuntimeError("Simulated MySQL confirmation failure")


def mock_confirm_failed(alert_id, claim_token):
    assert alert_id == 102
    assert claim_token == "token-102"
    return True


with (
    patch.object(
        worker,
        "claim_pending_fallback_alerts",
        return_value=alerts,
    ),
    patch.object(
        worker,
        "confirm_fallback_alert_conflict",
        side_effect=mock_confirm_conflict,
    ),
    patch.object(
        worker,
        "confirm_fallback_alert_failed",
        side_effect=mock_confirm_failed,
    ),
):
    result = worker.run_fallback_worker(
        send_alert=mock_send,
        limit=2,
    )

assert processed == [101, 102], processed
print("[TEST] CONTINUED_AFTER_CONFIRMATION_ERROR= True")

assert result["claimed"] == 2, result
assert result["confirmation_errors"] == 1, result
assert result["failed"] == 1, result
assert result["conflicted"] == 0, result
assert result["sent"] == 0, result

print("[TEST] CONFIRMATION_ERROR_COUNT= True")
print("[TEST] NEXT_ALERT_PROCESSED= True")
print("[TEST] ALL PASS: Worker confirmation isolation")