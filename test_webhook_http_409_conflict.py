
import json
import threading
import uuid

from urllib.request import Request, urlopen
from urllib.error import HTTPError

from db import get_connection
from webhook_idempotency_http import (
    create_webhook_server,
)
from webhook_request_hash import (
    calculate_request_hash,
)


key_a = "HTTP409-" + str(uuid.uuid4())
key_b = "HTTP409-" + str(uuid.uuid4())


payload_a = {
    "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
    "alert_id": 1001,
    "notification_type": "OUTBOX_EXHAUSTED",
}

payload_same = {
    "notification_type": "OUTBOX_EXHAUSTED",
    "alert_id": 1001,
    "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
}

payload_changed = {
    "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
    "alert_id": 1001,
    "notification_type": "CERTIFICATE_EXPIRED",
}


def send_request(url, key, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=5) as response:
            return (
                response.status,
                json.loads(response.read()),
            )

    except HTTPError as exc:
        return (
            exc.code,
            json.loads(exc.read()),
        )


def get_record_count(table, key):
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


def get_saved_hash(key):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT REQUEST_HASH
                FROM WEBHOOK_IDEMPOTENCY
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))

            row = cursor.fetchone()
            return row["REQUEST_HASH"] if row else None

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


server = create_webhook_server()

thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)

thread.start()

try:
    url = (
        f"http://127.0.0.1:"
        f"{server.server_port}/webhook"
    )

    # 1. 首次请求
    code, body = send_request(
        url, key_a, payload_a
    )

    assert code == 200
    assert body["status"] == "PROCESSED"

    print("[TEST] FIRST_REQUEST_HTTP_200= True")

    # 2. 相同 Key、相同内容
    code, body = send_request(
        url, key_a, payload_same
    )

    assert code == 200
    assert body["status"] == "DUPLICATE"

    print("[TEST] DUPLICATE_REQUEST_HTTP_200= True")

    # 3. 相同 Key、不同内容
    code, body = send_request(
        url, key_a, payload_changed
    )

    assert code == 409
    assert body["status"] == "CONFLICT"

    print("[TEST] CONFLICT_REQUEST_HTTP_409= True")

    # 4. 验证冲突没有修改原始 Hash
    assert get_saved_hash(
        key_a
    ) == calculate_request_hash(payload_a)

    print("[TEST] ORIGINAL_HASH_UNCHANGED= True")

    # 5. 验证冲突没有增加业务记录
    assert get_record_count(
        "WEBHOOK_IDEMPOTENCY", key_a
    ) == 1

    assert get_record_count(
        "WEBHOOK_BUSINESS_TEST", key_a
    ) == 1

    print("[TEST] CONFLICT_NO_EXTRA_BUSINESS= True")

    # 6. 不同 Key 正常处理
    code, body = send_request(
        url, key_b, payload_changed
    )

    assert code == 200
    assert body["status"] == "PROCESSED"

    print("[TEST] DIFFERENT_KEY_HTTP_200= True")

    # 7. 非法请求：缺少 Key
    code, body = send_request(
        url, "", payload_a
    )

    assert code == 400
    assert body["status"] == "BAD_REQUEST"

    print("[TEST] MISSING_KEY_HTTP_400= True")

    print("[TEST] ALL PASS: HTTP 409 conflict")

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

    cleanup([key_a, key_b])
