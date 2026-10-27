
import json
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from db import get_connection
from webhook_idempotency_http import create_webhook_server
from webhook_request_hash import calculate_request_hash


EVENT_TYPE = "JOB_OUTBOX_FALLBACK_ALERT"

key = "CONCURRENT-" + str(uuid.uuid4())

payload_a = {
    "event_type": EVENT_TYPE,
    "alert_id": 1001,
    "notification_type": "OUTBOX_EXHAUSTED",
}

payload_b = {
    "event_type": EVENT_TYPE,
    "alert_id": 1001,
    "notification_type": "CERTIFICATE_EXPIRED",
}

# 保证两个测试请求内容确实不同
assert calculate_request_hash(payload_a) != (
    calculate_request_hash(payload_b)
)


def send_request(url, key, payload, barrier):
    # 两个发送线程到齐后同时发起请求
    barrier.wait(timeout=10)

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
        with urlopen(request, timeout=10) as response:
            return (
                response.status,
                json.loads(response.read()),
            )

    except HTTPError as exc:
        return (
            exc.code,
            json.loads(exc.read()),
        )


def get_database_state(key):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT REQUEST_HASH
                FROM WEBHOOK_IDEMPOTENCY
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))

            hash_rows = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS TOTAL
                FROM WEBHOOK_BUSINESS_TEST
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))

            business_count = cursor.fetchone()["TOTAL"]

        return hash_rows, business_count

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


server = create_webhook_server()

server_thread = threading.Thread(
    target=server.serve_forever,
    daemon=True,
)

server_thread.start()

try:
    url = (
        f"http://127.0.0.1:"
        f"{server.server_port}/webhook"
    )

    barrier = threading.Barrier(2)

    # 1. 并发发送两个不同 Payload
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            send_request,
            url,
            key,
            payload_a,
            barrier,
        )

        future_b = executor.submit(
            send_request,
            url,
            key,
            payload_b,
            barrier,
        )

        result_a = future_a.result(timeout=15)
        result_b = future_b.result(timeout=15)

    results = [result_a, result_b]

    print("[TEST] RESULT_A=", result_a)
    print("[TEST] RESULT_B=", result_b)

    # 2. 必须恰好一个成功、一个冲突
    codes = sorted(result[0] for result in results)

    assert codes == [200, 409], results

    print("[TEST] ONE_PROCESSED_ONE_CONFLICT= True")

    # 3. 验证响应内容
    statuses = sorted(
        result[1]["status"] for result in results
    )

    assert statuses == ["CONFLICT", "PROCESSED"]

    print("[TEST] HTTP_STATUSES_CORRECT= True")

    # 4. 数据库必须只有一条幂等记录
    hash_rows, business_count = get_database_state(key)

    assert len(hash_rows) == 1

    print("[TEST] ONE_IDEMPOTENCY_RECORD= True")

    # 5. 业务只能执行一次
    assert business_count == 1

    print("[TEST] BUSINESS_EXECUTED_ONCE= True")

    # 6. Hash 必须对应成功处理的 Payload
    successful_payload = (
        payload_a if result_a[0] == 200 else payload_b
    )

    expected_hash = calculate_request_hash(
        successful_payload
    )

    assert hash_rows[0]["REQUEST_HASH"] == expected_hash

    print("[TEST] SAVED_HASH_MATCHES_WINNER= True")

    print("[TEST] ALL PASS: HTTP concurrent conflict")

finally:
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)

    cleanup(key)
