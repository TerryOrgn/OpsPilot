
import json
import socket
import threading
import uuid
import pymysql

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.request import Request, urlopen
from http.client import RemoteDisconnected

from db import get_connection


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

        if not key:
            self.send_error(400, "Missing Idempotency-Key")
            return

        length = int(self.headers.get("Content-Length", 0))

        try:
            payload = json.loads(self.rfile.read(length))

            if payload.get("event_type") != EVENT_TYPE:
                self.send_error(400, "Invalid event type")
                return

            result = process_event(key)

        except Exception:
            self.send_error(500, "Processing failed")
            return

        with request_lock:
            request_count += 1
            current_request = request_count

        # 第一次请求：事务已提交，但不返回 HTTP 响应
        if current_request == 1:
            self.close_connection = True

            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            self.connection.close()
            return

        # 第二次请求：正常返回
        body = json.dumps({
            "status": result,
            "alert_id": payload.get("alert_id"),
        }).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def send_request(url, key, alert_id):
    payload = {
        "event_type": EVENT_TYPE,
        "alert_id": alert_id,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": key,
        },
        method="POST",
    )

    with urlopen(request, timeout=5) as response:
        assert response.status == 200
        return json.loads(response.read())


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


def cleanup(key):
    conn = get_connection()

    try:
        conn.begin()

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

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


key = "RESPONSE-LOST-" + str(uuid.uuid4())

server = ThreadingHTTPServer(
    ("127.0.0.1", 0),
    WebhookHandler,
)

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)

server_thread.start()

try:
    url = f"http://127.0.0.1:{server.server_port}/webhook"

    # 1. 首次请求：预期连接被关闭
    try:
        send_request(url, key, 1001)
        raise AssertionError(
            "Expected HTTP response loss"
        )
    except (
        RemoteDisconnected,
        ConnectionResetError,
        ConnectionAbortedError,
    ):
        print("[TEST] FIRST_RESPONSE_LOST= True")

    # 2. 确认首次业务已经提交
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key
    ) == 1

    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key
    ) == 1

    print("[TEST] FIRST_TRANSACTION_COMMITTED= True")

    # 3. 使用相同 Key 重试
    result = send_request(url, key, 1001)

    assert result["status"] == "DUPLICATE"
    assert result["alert_id"] == 1001

    print("[TEST] RETRY_RETURNED_DUPLICATE= True")

    # 4. 最终验证
    assert request_count == 2

    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key
    ) == 1

    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key
    ) == 1

    print("[TEST] BUSINESS_EXECUTED_ONCE= True")
    print("[TEST] ALL PASS: HTTP response lost retry")

finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)

    cleanup(key)
