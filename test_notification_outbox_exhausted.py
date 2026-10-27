
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_failed,
    requeue_due_failed_outbox_events,
)

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None


def read_event():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, RETRY_COUNT,
                       NEXT_RETRY_AT, CLAIM_TOKEN
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )
            row = cursor.fetchone()
            columns = [item[0] for item in cursor.description]
            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()


try:
    # 1. 创建已尝试两次、等待第三次领取的事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                    (
                        NOTIFICATION_TYPE,
                        EVENT_TYPE,
                        STATUS,
                        RETRY_COUNT
                    )
                VALUES (%s, %s, 'PENDING', 2)
                """,
                (notification_type, "DEAD_LETTER_DETECTED")
            )
            event_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 2. 第三次领取
    claimed = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(claimed) == 1
    assert claimed[0]["EVENT_ID"] == event_id

    token = claimed[0]["CLAIM_TOKEN"]
    row = read_event()

    assert row["STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 3

    print("[TEST] THIRD_ATTEMPT_COUNT= 3")

    # 3. 模拟第三次发送失败
    result = confirm_outbox_failed(event_id, token)
    assert result is True

    row = read_event()

    assert row["STATUS"] == "EXHAUSTED"
    assert row["RETRY_COUNT"] == 3
    assert row["NEXT_RETRY_AT"] is None
    assert row["CLAIM_TOKEN"] is None

    print("[TEST] FINAL_STATUS=", row["STATUS"])
    print("[TEST] NEXT_RETRY_AT_CLEARED= True")

    # 4. 最终失败事件不能重新入队
    requeued = requeue_due_failed_outbox_events(
        notification_type=notification_type,
        max_attempts=3
    )

    assert requeued == 0
    assert read_event()["STATUS"] == "EXHAUSTED"

    print("[TEST] EXHAUSTED_NOT_REQUEUED= True")

    # 5. 最终失败事件不能再次领取
    claimed_again = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert claimed_again == []

    print("[TEST] EXHAUSTED_NOT_RECLAIMED= True")
    print("[TEST] ALL PASS: Outbox exhausted")

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
