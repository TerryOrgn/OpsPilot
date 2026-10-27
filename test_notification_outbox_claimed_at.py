
from uuid import uuid4

from db import get_connection
from notification_outbox import claim_pending_outbox_events

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None

try:
    # 1. 创建独立测试事件
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

    # 2. 领取指定通知类型的事件
    claimed = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(claimed) == 1
    assert claimed[0]["EVENT_ID"] == event_id

    # 3. 从真实 MySQL 读取领取状态和时间
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIMED_AT
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )
            row = cursor.fetchone()

            if isinstance(row, dict):
                status = row["STATUS"]
                claimed_at = row["CLAIMED_AT"]
            else:
                status, claimed_at = row
    finally:
        conn.close()

    assert status == "PROCESSING"
    assert claimed_at is not None

    print("[TEST] EVENT_ID=", event_id)
    print("[TEST] STATUS=", status)
    print("[TEST] CLAIMED_AT=", claimed_at)
    print("[TEST] ALL PASS: Outbox claimed timestamp")

finally:
    # 只清理本次测试记录
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
