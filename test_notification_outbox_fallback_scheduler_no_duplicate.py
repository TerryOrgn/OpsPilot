
import json
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from db import get_connection
from notification_outbox_fallback_scheduler import run_fallback_cycle


received = []
cycles = []
two_cycles_done = threading.Event()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))

        received.append({
            "payload": payload,
            "key": self.headers["Idempotency-Key"],
        })

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def on_job_event(event):
    cycles.append(event)

    if len(cycles) >= 2:
        two_cycles_done.set()


def get_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, CLAIMED_AT
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

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
server_thread.start()

scheduler = BackgroundScheduler()
alert_id = None

try:
    # 创建唯一测试告警
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
        scheduler.add_listener(
            on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )

        # 测试专用：每秒执行一次
        scheduler.add_job(
            run_fallback_cycle,
            trigger="interval",
            seconds=1,
            id="fallback_no_duplicate",
            max_instances=1,
            coalesce=True,
        )

        scheduler.start()

        assert two_cycles_done.wait(timeout=8), (
            "Two scheduler cycles did not finish"
        )

        # 等待中的任务全部结束后再检查结果
        scheduler.shutdown(wait=True)

    assert len(cycles) >= 2
    assert all(
        event.code == EVENT_JOB_EXECUTED
        for event in cycles
    )
    print("[TEST] TWO_CYCLES_SUCCEEDED= True")

    row = get_alert(alert_id)

    assert row["STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None

    print("[TEST] MYSQL_SENT_ONCE= True")

    assert len(received) == 1
    assert received[0]["payload"]["alert_id"] == alert_id
    assert received[0]["key"] == str(alert_id)

    print("[TEST] WEBHOOK_SENT_ONCE= True")

    print("[TEST] ALL PASS: Fallback scheduler no duplicate")

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
