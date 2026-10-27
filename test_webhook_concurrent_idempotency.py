
import time
import uuid
import threading
import pymysql

from concurrent.futures import ThreadPoolExecutor

from db import get_connection


EVENT_TYPE = "JOB_OUTBOX_FALLBACK_ALERT"

# 让两个线程尽可能同时开始数据库操作
start_barrier = threading.Barrier(2)


def process_event(key):
    conn = None

    try:
        # 每个线程使用独立数据库连接
        conn = get_connection()

        start_barrier.wait(timeout=10)

        conn.begin()

        try:
            with conn.cursor() as cursor:
                # 1. 争抢相同的幂等键
                cursor.execute("""
                    INSERT INTO WEBHOOK_IDEMPOTENCY
                        (IDEMPOTENCY_KEY, EVENT_TYPE)
                    VALUES (%s, %s)
                """, (key, EVENT_TYPE))

                # 延长事务时间，增加竞争窗口
                time.sleep(0.5)

                # 2. 模拟业务写入
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
        if conn is not None:
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


key = "CONCURRENT-TEST-" + str(uuid.uuid4())

try:
    # 两个线程同时处理相同 Key
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(process_event, key)
            for _ in range(2)
        ]

        results = [
            future.result(timeout=15)
            for future in futures
        ]

    print("[TEST] RESULTS=", sorted(results))

    # 一个成功，一个重复
    assert sorted(results) == [
        "DUPLICATE",
        "PROCESSED",
    ]

    print("[TEST] ONE_PROCESSED_ONE_DUPLICATE= True")

    # 幂等表只允许一条记录
    assert count_records(
        "WEBHOOK_IDEMPOTENCY", key
    ) == 1

    print("[TEST] IDEMPOTENCY_RECORD_ONCE= True")

    # 模拟业务只能执行一次
    assert count_records(
        "WEBHOOK_BUSINESS_TEST", key
    ) == 1

    print("[TEST] BUSINESS_RECORD_ONCE= True")

    print("[TEST] ALL PASS: Concurrent idempotency")

finally:
    cleanup(key)
