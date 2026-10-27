
import json
import threading
import urllib.request
import urllib.error
from unittest.mock import patch

import webhook_idempotency_http as webhook_http
from webhook_metrics import webhook_metrics


server = None
server_thread = None


def post_webhook(url, payload):
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": "metrics-test-key",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=5,
        ) as response:
            return response.status

    except urllib.error.HTTPError as exc:
        return exc.code


payload = {
    "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
    "alert_id": 935,
}


try:
    webhook_metrics.reset()

    server = webhook_http.create_webhook_server(
        host="127.0.0.1",
        port=0,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    server_thread.start()

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/webhook"

    # 1. PROCESSED
    with patch.object(
        webhook_http,
        "process_webhook_event",
        return_value="PROCESSED",
    ):
        assert post_webhook(url, payload) == 200

    # 2. DUPLICATE
    with patch.object(
        webhook_http,
        "process_webhook_event",
        return_value="DUPLICATE",
    ):
        assert post_webhook(url, payload) == 200

    # 3. CONFLICT
    with patch.object(
        webhook_http,
        "process_webhook_event",
        return_value="CONFLICT",
    ):
        assert post_webhook(url, payload) == 409

    # 4. ERROR
    with patch.object(
        webhook_http,
        "process_webhook_event",
        side_effect=RuntimeError("Simulated DB error"),
    ):
        assert post_webhook(url, payload) == 500

    result = webhook_metrics.snapshot()

    assert result == {
        "processed_total": 1,
        "duplicate_total": 1,
        "conflict_total": 1,
        "error_total": 1,
    }, result

    print("[TEST] PROCESSED_METRIC= True")
    print("[TEST] DUPLICATE_METRIC= True")
    print("[TEST] CONFLICT_METRIC= True")
    print("[TEST] ERROR_METRIC= True")
    print("[TEST] ALL PASS: HTTP metrics integration")

finally:
    if server is not None:
        server.shutdown()
        server.server_close()

    if server_thread is not None:
        server_thread.join(timeout=5)

    webhook_metrics.reset()
