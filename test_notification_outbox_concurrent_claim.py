
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from db import get_connection
from notification_outbox import claim_pending_outbox_events

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None

# 确保两个线程同时开始领取
barrier = Barrier(2)


def worker():
    barrier.wait(timeout=10)
    return claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )


try:
    # 1. 创建唯一测试事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                    (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                VALUES (%s, %s, 'PENDING')
                """,
                (notification_type, "DEAD_LETTER_DETECTED")
            )
            event_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 2. 两个线程并发领取
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]

    claimed_ids = [
        event["EVENT_ID"]
        for batch in results
        for event in batch
    ]

    # 3. 同一事件只能被领取一次
    assert claimed_ids == [event_id], (
        f"Unexpected claimed IDs: {claimed_ids}"
    )

    # 4. 验证数据库状态
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (event_id,)
            )
            row = cursor.fetchone()
            status = (
                row["STATUS"]
                if isinstance(row, dict)
                else row[0]
            )
    finally:
        conn.close()

    assert status == "PROCESSING"

    print("[TEST] EVENT_ID=", event_id)
    print("[TEST] WORKER_RESULTS=", [len(r) for r in results])
    print("[TEST] CLAIMED_IDS=", claimed_ids)
    print("[TEST] DB_STATUS=", status)
    print("[TEST] ALL PASS: Concurrent Outbox claim")

finally:
    # 仅清理本次测试创建的事件
    if event_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE EVENT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (event_id, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
