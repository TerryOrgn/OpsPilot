
import json
import os
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
)
from notification_outbox_fallback_scheduler import (
    run_fallback_cycle,
)


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

thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)
thread.start()

alert_id = None

try:
    # 1. 创建测试告警
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

    # 2. Worker A 领取，但不确认
    claimed = claim_pending_fallback_alerts(limit=1)

    assert len(claimed) == 1
    assert claimed[0]["ALERT_ID"] == alert_id

    first = get_alert(alert_id)
    assert first["STATUS"] == "PROCESSING"
    assert first["RETRY_COUNT"] == 1

    print("[TEST] WORKER_A_CLAIMED= True")

    # 3. 模拟 Worker A 崩溃后超过 300 秒
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 600 SECOND
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
            """, (alert_id,))
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    print("[TEST] STALE_PROCESSING_SIMULATED= True")

    # 4. 执行真实恢复 + 发送周期
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        result = run_fallback_cycle()

    assert result == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 0,
    }

    print("[TEST] RECOVERY_CYCLE_SUCCEEDED= True")

    # 5. 检查最终数据库状态
    final = get_alert(alert_id)

    assert final["STATUS"] == "SENT"
    assert final["RETRY_COUNT"] == 2
    assert final["CLAIM_TOKEN"] is None
    assert final["CLAIMED_AT"] is None

    print("[TEST] MYSQL_RECOVERED_TO_SENT= True")

    # 6. 检查 Webhook 投递
    assert len(received) == 1
    assert received[0]["payload"]["alert_id"] == alert_id
    assert received[0]["key"] == str(alert_id)

    print("[TEST] WEBHOOK_DELIVERED= True")
    print("[TEST] ALL PASS: Fallback crash recovery E2E")

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
