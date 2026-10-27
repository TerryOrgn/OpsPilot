
import json
import os
import socket
import threading
import uuid
import pymysql

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from unittest.mock import patch

from db import get_connection

from notification_outbox_fallback_dispatcher import (
    requeue_due_failed_fallback_alerts,
)
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)
from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)


EVENT_TYPE = "JOB_OUTBOX_FALLBACK_ALERT"

request_count = 0
request_lock = threading.Lock()


def process_event(key):
    conn = get_connection()

    try:
        conn.begin()

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO WEBHOOK_IDEMPOTENCY
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, EVENT_TYPE))

                cursor.execute("""
                    INSERT INTO WEBHOOK_BUSINESS_TEST
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, EVENT_TYPE))

            conn.commit()
            return "PROCESSED"

        except pymysql.err.IntegrityError as exc:
            conn.rollback()

            if exc.args[0] == 1062:
                return "DUPLICATE"

            raise

        except Exception:
            conn.rollback()
            raise

    finally:
        conn.close()


class WebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        global request_count

        key = self.headers.get("Idempotency-Key")
        length = int(self.headers.get("Content-Length", 0))

        try:
            payload = json.loads(self.rfile.read(length))

            if not key:
                self.send_error(400, "Missing key")
                return

            if payload.get("event_type") != EVENT_TYPE:
                self.send_error(400, "Invalid event type")
                return

            # 接收端真实 MySQL 事务
            result = process_event(key)

        except Exception:
            self.send_error(500, "Processing failed")
            return

        with request_lock:
            request_count += 1
            current = request_count

        # 第一次请求：业务已提交，故意丢失响应
        if current == 1:
            self.close_connection = True

            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            self.connection.close()
            return

        # 第二次请求：正常返回 HTTP 200
        body = json.dumps({
            "status": result,
            "alert_id": payload.get("alert_id"),
        }).encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type", "application/json"
        )
        self.send_header(
            "Content-Length", str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def get_alert(alert_id):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       NEXT_RETRY_AT, CLAIM_TOKEN
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))

            return cursor.fetchone()

    finally:
        conn.close()


def count_records(table, key):
    assert table in (
        "WEBHOOK_IDEMPOTENCY",
        "WEBHOOK_BUSINESS_TEST",
    )

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS TOTAL
                FROM {table}
                WHERE IDEMPOTENCY_KEY = %s
                """,
                (key,),
            )
            return cursor.fetchone()["TOTAL"]

    finally:
        conn.close()


def make_retry_due(alert_id):
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
key = None

try:
    # 1. 创建 Fallback 测试告警
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS,
                     NEW_STATUS, STATUS)
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

    key = str(alert_id)

    url = f"http://127.0.0.1:{server.server_port}/webhook"

    with patch.dict(
        os.environ,
        {"OPSPILOT_FALLBACK_WEBHOOK_URL": url},
    ):
        # 2. 第一次发送：HTTP 响应丢失
        first = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

        assert first["claimed"] == 1
        assert first["failed"] == 1
        assert first["sent"] == 0
        assert first["confirmation_errors"] == 0

        failed = get_alert(alert_id)

        assert failed["STATUS"] == "FAILED"
        assert failed["RETRY_COUNT"] == 1
        assert failed["NEXT_RETRY_AT"] is not None
        assert failed["CLAIM_TOKEN"] is None

        print("[TEST] FIRST_SEND_FAILED= True")

        # 3. 业务实际上已经提交
        assert count_records(
            "WEBHOOK_IDEMPOTENCY", key
        ) == 1

        assert count_records(
            "WEBHOOK_BUSINESS_TEST", key
        ) == 1

        print("[TEST] RECEIVER_BUSINESS_COMMITTED= True")

        # 4. 模拟重试时间到达
        make_retry_due(alert_id)

        requeued = requeue_due_failed_fallback_alerts()

        assert requeued == 1
        assert get_alert(alert_id)["STATUS"] == "PENDING"

        print("[TEST] FAILED_ALERT_REQUEUED= True")

        # 5. 第二次发送
        second = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

        assert second["claimed"] == 1
        assert second["sent"] == 1
        assert second["failed"] == 0
        assert second["confirmation_errors"] == 0

        print("[TEST] RETRY_SEND_SUCCEEDED= True")

    # 6. 最终数据库检查
    final = get_alert(alert_id)

    assert final["STATUS"] == "SENT"
    assert final["RETRY_COUNT"] == 2
    assert final["CLAIM_TOKEN"] is None

    assert request_count == 2

    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key
    ) == 1

    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key
    ) == 1

    print("[TEST] BUSINESS_EXECUTED_ONCE= True")
    print("[TEST] FALLBACK_FINAL_STATUS_SENT= True")
    print("[TEST] ALL PASS: Fallback E2E retry idempotency")

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

    if alert_id is not None:
        conn = get_connection()

        try:
            conn.begin()

            with conn.cursor() as cursor:
                if key is not None:
                    cursor.execute("""
                        DELETE FROM WEBHOOK_BUSINESS_TEST
                        WHERE IDEMPOTENCY_KEY = %s
                    """, (key,))

                    cursor.execute("""
                        DELETE FROM WEBHOOK_IDEMPOTENCY
                        WHERE IDEMPOTENCY_KEY = %s
                    """, (key,))

                cursor.execute("""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                """, (alert_id, "OUTBOX_EXHAUSTED"))

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()
