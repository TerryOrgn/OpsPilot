
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from unittest.mock import patch

from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 模拟接收端内部故障
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"Internal Server Error")

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
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    alert = {
        "ALERT_ID": 1002,
        "NOTIFICATION_TYPE": "OUTBOX_EXHAUSTED",
        "OLD_STATUS": "NORMAL",
        "NEW_STATUS": "ACTION_REQUIRED",
    }

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        try:
            send_fallback_webhook(alert)
        except HTTPError as exc:
            assert exc.code == 500
            print("[TEST] HTTP_500_RAISED= True")
        else:
            raise AssertionError(
                "HTTP 500 must raise HTTPError"
            )

    print("[TEST] NO_FALSE_SUCCESS= True")
    print("[TEST] ALL PASS: Fallback webhook HTTP 500")

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
