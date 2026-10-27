
import json
import os
import threading

from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from db import get_connection
from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
)


received = []


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


def run_one_scheduler_cycle():
    """
    创建一个新的调度器实例，
    自动执行一次真实 Fallback 周期，然后停止。
    """
    scheduler = BackgroundScheduler()
    finished = threading.Event()
    events = []

    def on_event(event):
        events.append(event)
        finished.set()

    scheduler.add_listener(
        on_event,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
    )

    scheduler.add_job(
        run_fallback_cycle,
        trigger="date",
        run_date=datetime.now() + timedelta(
            milliseconds=300
        ),
        id="fallback_restart_test",
    )

    try:
        scheduler.start()

        assert finished.wait(timeout=10), (
            "Scheduler cycle did not finish"
        )

    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)

    assert len(events) == 1
    assert events[0].code == EVENT_JOB_EXECUTED


server = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    WebhookHandler,
)

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
server_thread.start()

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
        # 调度器 A：首次发送
        run_one_scheduler_cycle()

        first = get_alert(alert_id)

        assert first["STATUS"] == "SENT"
        assert first["RETRY_COUNT"] == 1
        assert len(received) == 1

        print("[TEST] FIRST_SCHEDULER_SENT= True")

        # 调度器 B：模拟重新启动
        run_one_scheduler_cycle()

        second = get_alert(alert_id)

        assert second["STATUS"] == "SENT"
        assert second["RETRY_COUNT"] == 1
        assert second["CLAIM_TOKEN"] is None
        assert second["CLAIMED_AT"] is None

        print("[TEST] RESTART_PRESERVED_SENT= True")

        assert len(received) == 1
        assert received[0]["payload"]["alert_id"] == alert_id
        assert received[0]["key"] == str(alert_id)

        print("[TEST] NO_DUPLICATE_AFTER_RESTART= True")

    print("[TEST] ALL PASS: Fallback scheduler restart")

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
    server_thread.join(timeout=2)
