
import json
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from db import get_connection
from notification_outbox_fallback_worker import run_fallback_worker
from notification_outbox_fallback_webhook import send_fallback_webhook


received = []


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        received.append({
            "payload": json.loads(self.rfile.read(length)),
            "key": self.headers["Idempotency-Key"],
        })
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), WebhookHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

alert_id = None

try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS, NEW_STATUS, STATUS)
                VALUES (%s, %s, %s, 'PENDING')
            """, (
                "OUTBOX_EXHAUSTED",
                "NORMAL",
                "ACTION_REQUIRED",
            ))
            alert_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    url = f"http://127.0.0.1:{server.server_port}/webhook"

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        result = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

    assert result == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 0,
    }
    print("[TEST] WORKER_SENT= True")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT, CLAIM_TOKEN, CLAIMED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            row = cursor.fetchone()
    finally:
        conn.close()

    assert row["STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None
    print("[TEST] MYSQL_SENT_CONFIRMED= True")

    assert len(received) == 1
    assert received[0]["payload"]["alert_id"] == alert_id
    assert received[0]["key"] == str(alert_id)
    print("[TEST] WEBHOOK_RECEIVED= True")

    print("[TEST] ALL PASS: Fallback MySQL Webhook E2E")

finally:
    if alert_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                """, (alert_id, "OUTBOX_EXHAUSTED"))
            conn.commit()
        finally:
            conn.close()

    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
