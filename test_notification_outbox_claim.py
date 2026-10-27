
from uuid import uuid4

from db import get_connection
from notification_outbox import claim_pending_outbox_events

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None

try:
    # 1. 创建测试事件
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

    # 2. 第一次领取
    claimed = claim_pending_outbox_events(limit=100)

    matched = [
        event for event in claimed
        if event["EVENT_ID"] == event_id
    ]

    assert len(matched) == 1

    # 3. 验证数据库状态
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

    # 4. 第二次领取不能重复获得该事件
    claimed_again = claim_pending_outbox_events(limit=100)

    assert event_id not in {
        event["EVENT_ID"] for event in claimed_again
    }

    print("[TEST] EVENT_ID=", event_id)
    print("[TEST] FIRST_CLAIM= SUCCESS")
    print("[TEST] DB_STATUS=", status)
    print("[TEST] DUPLICATE_CLAIM= NONE")
    print("[TEST] ALL PASS: Outbox claim")

finally:
    # 5. 清理本次测试事件
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
