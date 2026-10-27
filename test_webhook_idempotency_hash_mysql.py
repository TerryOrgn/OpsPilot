
import uuid

from db import get_connection
from webhook_idempotency_processor import process_webhook_event


key_a = "HASH-TEST-" + str(uuid.uuid4())
key_b = "HASH-TEST-" + str(uuid.uuid4())


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


try:
    # 1. 首次请求
    result = process_webhook_event(key_a, payload_a)

    assert result == "PROCESSED"
    print("[TEST] FIRST_REQUEST_PROCESSED= True")

    # 2. 相同 Key、相同内容，但 JSON 字段顺序不同
    result = process_webhook_event(key_a, payload_same)

    assert result == "DUPLICATE"
    print("[TEST] SAME_KEY_SAME_HASH_DUPLICATE= True")

    # 3. 相同 Key、不同内容
    result = process_webhook_event(key_a, payload_changed)

    assert result == "CONFLICT"
    print("[TEST] SAME_KEY_DIFFERENT_HASH_CONFLICT= True")

    # 4. 不同 Key 可以正常处理
    result = process_webhook_event(key_b, payload_changed)

    assert result == "PROCESSED"
    print("[TEST] DIFFERENT_KEY_PROCESSED= True")

    # 5. 数据库记录数量验证
    for key in (key_a, key_b):
        assert count_records(
            "WEBHOOK_IDEMPOTENCY", key
        ) == 1

        assert count_records(
            "WEBHOOK_BUSINESS_TEST", key
        ) == 1

    print("[TEST] BUSINESS_RECORDS_NOT_DUPLICATED= True")

    # 6. 验证请求指纹已持久化
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT REQUEST_HASH
                FROM WEBHOOK_IDEMPOTENCY
                WHERE IDEMPOTENCY_KEY = %s
            """, (key_a,))

            row = cursor.fetchone()

            assert row is not None
            assert row["REQUEST_HASH"] is not None
            assert len(row["REQUEST_HASH"]) == 64
    finally:
        conn.close()

    print("[TEST] REQUEST_HASH_PERSISTED= True")
    print("[TEST] ALL PASS: MySQL request hash idempotency")

finally:
    cleanup([key_a, key_b])
