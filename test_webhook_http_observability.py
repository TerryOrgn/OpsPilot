
import json
import threading
import urllib.request
import uuid
from unittest.mock import patch

from db import get_connection
import webhook_idempotency_http as webhook_http


key = f"obs-{uuid.uuid4()}"
results = []
server = None
server_thread = None


def get_business_count():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS TOTAL
                FROM WEBHOOK_BUSINESS_TEST
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
            return cursor.fetchone()["TOTAL"]
    finally:
        conn.close()


def cleanup():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM WEBHOOK_BUSINESS_TEST
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
            cursor.execute("""
                DELETE FROM WEBHOOK_IDEMPOTENCY
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
        conn.commit()
    finally:
        conn.close()


original_processor = webhook_http.process_webhook_event


def observed_processor(idempotency_key, payload):
    result = original_processor(idempotency_key, payload)
    results.append(result)
    return result


def post_webhook(url, payload):
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": key,
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=5,
    ) as response:
        return response.status


payload = {
    "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
    "alert_id": 933,
    "notification_type": "OUTBOX_EXHAUSTED",
    "old_status": "NORMAL",
    "new_status": "ACTION_REQUIRED",
}


try:
    with patch.object(
        webhook_http,
        "process_webhook_event",
        side_effect=observed_processor,
    ):
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

        first_status = post_webhook(url, payload)
        second_status = post_webhook(url, payload)

    assert first_status == 200, first_status
    assert second_status == 200, second_status

    assert results == [
        "PROCESSED",
        "DUPLICATE",
    ], results

    assert get_business_count() == 1

    print("[TEST] FIRST_HTTP_STATUS= 200")
    print("[TEST] FIRST_RESULT= PROCESSED")
    print("[TEST] SECOND_HTTP_STATUS= 200")
    print("[TEST] SECOND_RESULT= DUPLICATE")
    print("[TEST] HTTP_REQUEST_COUNT= 2")
    print("[TEST] BUSINESS_COUNT= 1")
    print("[TEST] ALL PASS: HTTP idempotency observability")

finally:
    if server is not None:
        server.shutdown()
        server.server_close()

    if server_thread is not None:
        server_thread.join(timeout=5)

    cleanup()
