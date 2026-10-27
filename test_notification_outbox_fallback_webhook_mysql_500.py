
import os
import threading

from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from db import get_connection
from notification_outbox_fallback_worker import run_fallback_worker
from notification_outbox_fallback_webhook import send_fallback_webhook


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

alert_id = None

try:
    # 创建测试告警
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

    # 执行真实 Worker + Webhook HTTP 500
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
        "sent": 0,
        "failed": 1,
        "confirmation_errors": 0,
    }
    print("[TEST] WORKER_FAILED= True")

    # 检查真实 MySQL 状态
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, CLAIMED_AT,
                       NEXT_RETRY_AT, UPDATED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            row = cursor.fetchone()
    finally:
        conn.close()

    assert row["STATUS"] == "FAILED"
    assert row["RETRY_COUNT"] == 1
    print("[TEST] MYSQL_FAILED_CONFIRMED= True")

    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None
    print("[TEST] CLAIM_CLEARED= True")

    assert row["NEXT_RETRY_AT"] is not None

    delay = (
        row["NEXT_RETRY_AT"] - row["UPDATED_AT"]
    ).total_seconds()

    assert 59 <= delay <= 61, f"Unexpected retry delay: {delay}"
    print("[TEST] RETRY_60_SECONDS= True")

    print("[TEST] ALL PASS: Fallback MySQL Webhook HTTP 500")

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
