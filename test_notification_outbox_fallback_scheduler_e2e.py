
import json
import os
import threading

from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler

from db import get_connection
from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
)


received = []
delivered = threading.Event()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])

        received.append({
            "payload": json.loads(self.rfile.read(length)),
            "key": self.headers["Idempotency-Key"],
        })

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

        delivered.set()

    def log_message(self, format, *args):
        pass


server = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    WebhookHandler,
)

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
server_thread.start()

scheduler = BackgroundScheduler()
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

    url = f"http://127.0.0.1:{server.server_port}/webhook"

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        # 测试专用：立即触发一次
        scheduler.add_job(
            run_fallback_cycle,
            trigger="date",
            run_date=datetime.now() + timedelta(
                milliseconds=300
            ),
            id="fallback_e2e",
        )

        scheduler.start()

        assert delivered.wait(timeout=10), (
            "Webhook was not called within 10 seconds"
        )

        # 等待 Worker 完成数据库确认
        import time

        deadline = time.monotonic() + 5

        while True:
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT STATUS, RETRY_COUNT,
                               CLAIM_TOKEN, CLAIMED_AT
                        FROM JOB_OUTBOX_FALLBACK_ALERT
                        WHERE ALERT_ID = %s
                    """, (alert_id,))
                    row = cursor.fetchone()
            finally:
                conn.close()

            if row["STATUS"] == "SENT":
                break

            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"Expected SENT, got {row['STATUS']}"
                )

            time.sleep(0.1)

    print("[TEST] SCHEDULER_TRIGGERED= True")

    assert len(received) == 1
    assert received[0]["payload"]["alert_id"] == alert_id
    assert received[0]["key"] == str(alert_id)

    print("[TEST] WEBHOOK_RECEIVED= True")

    assert row["STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None

    print("[TEST] MYSQL_SENT_CONFIRMED= True")

    print("[TEST] ALL PASS: Fallback scheduler E2E")

finally:
    if scheduler.running:
        scheduler.shutdown(wait=True)

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
    server_thread.join(timeout=2)
