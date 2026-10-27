
import pymysql

from db import get_connection
from webhook_request_hash import calculate_request_hash


EVENT_TYPE = "JOB_OUTBOX_FALLBACK_ALERT"


def process_webhook_event(key: str, payload: dict) -> str:
    if not isinstance(key, str) or not key or len(key) > 128:
        raise ValueError("Invalid Idempotency-Key")

    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    if payload.get("event_type") != EVENT_TYPE:
        raise ValueError("Invalid event_type")

    request_hash = calculate_request_hash(payload)

    conn = get_connection()

    try:
        conn.begin()

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO WEBHOOK_IDEMPOTENCY
                        (IDEMPOTENCY_KEY, EVENT_TYPE, REQUEST_HASH)
                    VALUES (%s, %s, %s)
                """, (key, EVENT_TYPE, request_hash))

                cursor.execute("""
                    INSERT INTO WEBHOOK_BUSINESS_TEST
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, EVENT_TYPE))

            conn.commit()
            return "PROCESSED"

        except pymysql.err.IntegrityError as exc:
            conn.rollback()

            # 只有 MySQL 1062 表示唯一键冲突
            if exc.args[0] != 1062:
                raise

            # 回滚后重新读取已提交的幂等记录
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT REQUEST_HASH
                    FROM WEBHOOK_IDEMPOTENCY
                    WHERE IDEMPOTENCY_KEY = %s
                """, (key,))

                existing = cursor.fetchone()

            if existing is None:
                raise RuntimeError(
                    "Duplicate key detected but record not found"
                )

            existing_hash = existing["REQUEST_HASH"]

            if existing_hash is None:
                # 兼容旧记录：不能安全判断是否为相同请求
                return "CONFLICT"

            if existing_hash == request_hash:
                return "DUPLICATE"

            return "CONFLICT"

        except Exception:
            conn.rollback()
            raise

    finally:
        conn.close()
