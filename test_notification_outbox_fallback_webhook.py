
import json
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)

received = []


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)

        received.append({
            "payload": json.loads(body),
            "content_type": self.headers["Content-Type"],
            "idempotency_key": self.headers["Idempotency-Key"],
        })

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

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

try:
    url = (
        f"http://127.0.0.1:{server.server_port}/webhook"
    )

    alert = {
        "ALERT_ID": 1001,
        "NOTIFICATION_TYPE": "OUTBOX_EXHAUSTED",
        "OLD_STATUS": "NORMAL",
        "NEW_STATUS": "ACTION_REQUIRED",
    }

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        result = send_fallback_webhook(alert)

    assert result is True
    print("[TEST] HTTP_200_ACCEPTED= True")

    assert len(received) == 1
    print("[TEST] POST_RECEIVED= True")

    payload = received[0]["payload"]

    assert payload == {
        "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
        "alert_id": 1001,
        "notification_type": "OUTBOX_EXHAUSTED",
        "old_status": "NORMAL",
        "new_status": "ACTION_REQUIRED",
    }
    print("[TEST] JSON_PAYLOAD_VALID= True")

    assert received[0]["content_type"] == "application/json"
    assert received[0]["idempotency_key"] == "1001"
    print("[TEST] IDEMPOTENCY_HEADER_VALID= True")

    print("[TEST] ALL PASS: Fallback webhook HTTP 200")

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
