
import json

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)

from webhook_idempotency_processor import (
    process_webhook_event,
)
from webhook_metrics import webhook_metrics

class WebhookHandler(BaseHTTPRequestHandler):

    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/webhook":
            self.send_json(404, {
                "status": "NOT_FOUND",
            })
            return

        key = self.headers.get("Idempotency-Key")

        if not key:
            self.send_json(400, {
                "status": "BAD_REQUEST",
                "message": "Missing Idempotency-Key",
            })
            return

        try:
            length = int(
                self.headers.get("Content-Length", "0")
            )

            if length <= 0 or length > 65536:
                raise ValueError("Invalid Content-Length")

            payload = json.loads(
                self.rfile.read(length)
            )

            result = process_webhook_event(
                key,
                payload,
            )

        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {
                "status": "BAD_REQUEST",
                "message": str(exc),
            })
            return

        except Exception:
            webhook_metrics.record("ERROR")
            self.send_json(500, {
                "status": "INTERNAL_ERROR",
            })
            return

        if result == "CONFLICT":
            webhook_metrics.record("CONFLICT")
            self.send_json(409, {
                "status": "CONFLICT",
                "message": (
                    "Idempotency-Key reused "
                    "with different payload"
                ),
            })
            return

        if result in ("PROCESSED", "DUPLICATE"):
            webhook_metrics.record(result)
            self.send_json(200, {
                "status": result,
            })
            return

        webhook_metrics.record("ERROR")

        self.send_json(500, {
            "status": "INTERNAL_ERROR",
        })

    def do_GET(self):
        if self.path == "/metrics":
            self.send_json(
                200,
                webhook_metrics.snapshot(),
            )
            return

        self.send_json(404, {
            "status": "NOT_FOUND",
        })
        
    def log_message(self, format, *args):
        pass


def create_webhook_server(
    host="127.0.0.1",
    port=0,
):
    return ThreadingHTTPServer(
        (host, port),
        WebhookHandler,
    )
    