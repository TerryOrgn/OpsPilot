
import json
import threading

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.request import Request, urlopen


processed_keys = set()
received_count = 0
business_count = 0

# 多线程 HTTP Server 需要锁保护共享状态
lock = threading.Lock()


class IdempotentWebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        global received_count, business_count

        key = self.headers.get("Idempotency-Key")

        if not key:
            self.send_response(400)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))

        try:
            payload = json.loads(
                self.rfile.read(length)
            )
        except (ValueError, UnicodeDecodeError):
            self.send_response(400)
            self.end_headers()
            return

        with lock:
            received_count += 1

            if key in processed_keys:
                duplicate = True
            else:
                duplicate = False

                # 模拟业务处理
                business_count += 1

                # 记录已处理 Key
                processed_keys.add(key)

        response = {
            "duplicate": duplicate,
            "alert_id": payload.get("alert_id"),
        }

        body = json.dumps(response).encode("utf-8")

        self.send_response(200)
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

    def log_message(self, format, *args):
        pass


def send_webhook(url, alert_id):
    payload = {
        "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
        "alert_id": alert_id,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(alert_id),
        },
        method="POST",
    )

    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read())


server = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    IdempotentWebhookHandler,
)

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
server_thread.start()

try:
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    # 1. 第一次发送 Alert 1001
    first = send_webhook(url, 1001)

    assert first["duplicate"] is False
    assert received_count == 1
    assert business_count == 1

    print("[TEST] FIRST_REQUEST_PROCESSED= True")

    # 2. 第二次发送相同 Alert 1001
    second = send_webhook(url, 1001)

    assert second["duplicate"] is True
    assert received_count == 2
    assert business_count == 1

    print("[TEST] DUPLICATE_REQUEST_DETECTED= True")
    print("[TEST] BUSINESS_EXECUTED_ONCE= True")

    # 3. 发送不同的 Alert 1002
    third = send_webhook(url, 1002)

    assert third["duplicate"] is False
    assert received_count == 3
    assert business_count == 2

    print("[TEST] DIFFERENT_KEY_PROCESSED= True")

    # 4. 最终验证
    assert processed_keys == {"1001", "1002"}

    print("[TEST] ALL PASS: Webhook idempotency")

finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)
