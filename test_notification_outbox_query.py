
from uuid import uuid4

from db import get_connection
from notification_outbox import get_pending_outbox_events

notification_type = "T_" + uuid4().hex[:20].upper()

conn = get_connection()

try:
    # 插入一条临时测试事件
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
            VALUES (%s, %s, %s)
            """,
            (
                notification_type,
                "DEAD_LETTER_DETECTED",
                "PENDING"
            )
        )
        event_id = cursor.lastrowid

    conn.commit()

    # 调用真实查询函数
    events = get_pending_outbox_events(limit=100)

    # 只检查本次创建的测试事件
    matched = [
        event for event in events
        if event["EVENT_ID"] == event_id
    ]

    assert len(matched) == 1

    event = matched[0]

    assert event["NOTIFICATION_TYPE"] == notification_type
    assert event["EVENT_TYPE"] == "DEAD_LETTER_DETECTED"
    assert event["STATUS"] == "PENDING"

    print("[TEST] EVENT_ID=", event_id)
    print("[TEST] EVENT_TYPE=", event["EVENT_TYPE"])
    print("[TEST] STATUS=", event["STATUS"])
    print("[TEST] ALL PASS: Outbox pending query")

finally:
    # 清理本次测试事件
    try:
        conn.rollback()
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
