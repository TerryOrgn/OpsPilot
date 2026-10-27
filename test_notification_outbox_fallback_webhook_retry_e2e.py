
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from db import get_connection
from notification_outbox_fallback_worker import run_fallback_worker
from notification_outbox_fallback_webhook import send_fallback_webhook
from notification_outbox_fallback_dispatcher import (
    requeue_due_failed_fallback_alerts,
)


received = []


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)

        received.append(self.headers["Idempotency-Key"])

        # 第一次失败，第二次成功
        status = 500 if len(received) == 1 else 200
        self.send_response(status)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def get_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, CLAIMED_AT,
                       NEXT_RETRY_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            return cursor.fetchone()
    finally:
        conn.close()


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
        # 第一次：HTTP 500
        first = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

        assert first == {
            "claimed": 1,
            "sent": 0,
            "failed": 1,
            "confirmation_errors": 0,
        }

        row = get_alert(alert_id)
        assert row["STATUS"] == "FAILED"
        assert row["RETRY_COUNT"] == 1
        assert row["NEXT_RETRY_AT"] is not None

        print("[TEST] FIRST_ATTEMPT_FAILED= True")

        # 未到重试时间，不应重新入队
        requeue_due_failed_fallback_alerts()
        assert get_alert(alert_id)["STATUS"] == "FAILED"

        print("[TEST] EARLY_REQUEUE_BLOCKED= True")

        # 只调整测试记录的重试时间
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE JOB_OUTBOX_FALLBACK_ALERT
                    SET NEXT_RETRY_AT =
                        CURRENT_TIMESTAMP(3) - INTERVAL 1 SECOND
                    WHERE ALERT_ID = %s
                      AND STATUS = 'FAILED'
                """, (alert_id,))
                assert cursor.rowcount == 1
            conn.commit()
        finally:
            conn.close()

        requeue_due_failed_fallback_alerts()
        assert get_alert(alert_id)["STATUS"] == "PENDING"

        print("[TEST] DUE_REQUEUE_SUCCESS= True")

        # 第二次：HTTP 200
        second = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

        assert second == {
            "claimed": 1,
            "sent": 1,
            "failed": 0,
            "confirmation_errors": 0,
        }

    row = get_alert(alert_id)
    assert row["STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 2
    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None

    print("[TEST] SECOND_ATTEMPT_SENT= True")

    assert received == [str(alert_id), str(alert_id)]
    print("[TEST] IDEMPOTENCY_KEY_STABLE= True")

    print("[TEST] ALL PASS: Webhook retry E2E")

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
