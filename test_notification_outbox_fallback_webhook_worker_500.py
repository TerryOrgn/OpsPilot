
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"Simulated failure")

    def log_message(self, format, *args):
        pass


server = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    WebhookHandler,
)

thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
thread.start()

alert = {
    "ALERT_ID": 1003,
    "NOTIFICATION_TYPE": "OUTBOX_EXHAUSTED",
    "OLD_STATUS": "NORMAL",
    "NEW_STATUS": "ACTION_REQUIRED",
    "CLAIM_TOKEN": "test-token-1003",
}

try:
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    with (
        patch.dict(
            os.environ,
            {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
        ),
        patch(
            "notification_outbox_fallback_worker."
            "claim_pending_fallback_alerts",
            return_value=[alert],
        ),
        patch(
            "notification_outbox_fallback_worker."
            "confirm_fallback_alert_failed",
            return_value=True,
        ) as mock_failed,
        patch(
            "notification_outbox_fallback_worker."
            "confirm_fallback_alert_sent",
            return_value=True,
        ) as mock_sent,
    ):
        result = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

        assert result == {
            "claimed": 1,
            "sent": 0,
            "failed": 1,
            "confirmation_errors": 0,
        }
        print("[TEST] WEBHOOK_500_COUNTED_AS_FAILURE= True")

        mock_failed.assert_called_once_with(
            1003,
            "test-token-1003",
        )
        print("[TEST] FAILURE_CONFIRM_CALLED= True")

        mock_sent.assert_not_called()
        print("[TEST] SUCCESS_CONFIRM_NOT_CALLED= True")

    print("[TEST] ALL PASS: Webhook worker HTTP 500")

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
