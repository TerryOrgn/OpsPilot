
import json
import threading
import uuid
import pymysql

from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.request import Request, urlopen

from db import get_connection


EVENT_TYPE = "JOB_OUTBOX_FALLBACK_ALERT"


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


def start_server():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        WebhookHandler,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    return server, thread


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def send_request(server, key, alert_id):
    url = f"http://127.0.0.1:{server.server_port}/webhook"

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


def cleanup(keys):
    conn = get_connection()
    try:
        conn.begin()

        with conn.cursor() as cursor:
            for key in keys:
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


key_a = "HTTP-TEST-" + str(uuid.uuid4())
key_b = "HTTP-TEST-" + str(uuid.uuid4())

server_a = None
server_b = None

try:
    # 1. Server A 首次处理
    server_a, thread_a = start_server()

    first = send_request(server_a, key_a, 1001)

    assert first["status"] == "PROCESSED"
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_a
    ) == 1

    print("[TEST] FIRST_HTTP_REQUEST_PROCESSED= True")

    # 2. 关闭 Server A
    stop_server(server_a, thread_a)
    server_a = None

    # 3. 创建新的 Server B
    server_b, thread_b = start_server()

    # 4. 相同 Key 再次请求
    duplicate = send_request(server_b, key_a, 1001)

    assert duplicate["status"] == "DUPLICATE"
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key_a
    ) == 1
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_a
    ) == 1

    print("[TEST] DUPLICATE_AFTER_SERVER_RESTART= True")

    # 5. 不同 Key 正常处理
    second = send_request(server_b, key_b, 1002)

    assert second["status"] == "PROCESSED"
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key_b
    ) == 1
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_b
    ) == 1

    print("[TEST] DIFFERENT_KEY_PROCESSED= True")

    print("[TEST] ALL PASS: HTTP MySQL idempotency")

finally:
    if server_a is not None:
        stop_server(server_a, thread_a)

    if server_b is not None:
        stop_server(server_b, thread_b)

    cleanup((key_a, key_b))
