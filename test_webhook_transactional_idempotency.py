
import uuid

import pymysql

from db import get_connection


def process_event(key, simulate_failure=False):
    conn = get_connection()

    try:
        conn.begin()

        try:
            with conn.cursor() as cursor:
                # 1. 先领取幂等键
                cursor.execute("""
                    INSERT INTO WEBHOOK_IDEMPOTENCY
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, "JOB_OUTBOX_FALLBACK_ALERT"))

                # 2. 模拟业务处理
                cursor.execute("""
                    INSERT INTO WEBHOOK_BUSINESS_TEST
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, "JOB_OUTBOX_FALLBACK_ALERT"))

                # 3. 模拟业务失败
                if simulate_failure:
                    raise RuntimeError(
                        "Simulated business failure"
                    )

            conn.commit()
            return "PROCESSED"

        except pymysql.err.IntegrityError as exc:
            conn.rollback()

            # 1062 = MySQL duplicate key
            if exc.args[0] == 1062:
                return "DUPLICATE"

            raise

        except Exception:
            conn.rollback()
            raise

    finally:
        conn.close()


def count_records(table, key):
    # 表名只能使用测试代码中的固定白名单
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


key_success = "TEST-" + str(uuid.uuid4())
key_failure = "TEST-" + str(uuid.uuid4())

try:
    # 测试 1：首次处理成功
    result = process_event(key_success)

    assert result == "PROCESSED"
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key_success
    ) == 1
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_success
    ) == 1

    print("[TEST] FIRST_TRANSACTION_COMMITTED= True")

    # 测试 2：重复请求
    result = process_event(key_success)

    assert result == "DUPLICATE"
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_success
    ) == 1

    print("[TEST] DUPLICATE_BUSINESS_PREVENTED= True")

    # 测试 3：模拟业务失败
    try:
        process_event(
            key_failure,
            simulate_failure=True,
        )
        raise AssertionError(
            "Expected simulated failure"
        )
    except RuntimeError as exc:
        assert str(exc) == "Simulated business failure"

    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key_failure
    ) == 0
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_failure
    ) == 0

    print("[TEST] FAILED_TRANSACTION_ROLLED_BACK= True")

    # 测试 4：失败后重试
    result = process_event(key_failure)

    assert result == "PROCESSED"
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key_failure
    ) == 1
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key_failure
    ) == 1

    print("[TEST] RETRY_AFTER_ROLLBACK_SUCCEEDED= True")

    print("[TEST] ALL PASS: Transactional idempotency")

finally:
    # 清理本次测试数据
    conn = get_connection()
    try:
        conn.begin()

        with conn.cursor() as cursor:
            for key in (key_success, key_failure):
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
