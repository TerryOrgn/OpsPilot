
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_sent,
    confirm_outbox_failed,
    recover_stale_outbox_events,
)

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None


def read_event():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
                    CLAIMED_AT,
                    CLAIM_TOKEN,
                    NEXT_RETRY_AT
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
    # 1. 创建已尝试两次的待领取事件
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

    old_token = claimed[0]["CLAIM_TOKEN"]

    row = read_event()
    assert row["STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 3

    print("[TEST] THIRD_ATTEMPT_COUNT= 3")

    # 3. 模拟10分钟前领取
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )

        conn.commit()
    finally:
        conn.close()

    # 4. 执行超时恢复
    # 注意：此函数会扫描整个 Outbox 表
    recover_stale_outbox_events(
        timeout_seconds=300,
        max_attempts=3
    )

    row = read_event()

    assert row["STATUS"] == "EXHAUSTED"
    assert row["RETRY_COUNT"] == 3
    assert row["CLAIMED_AT"] is None
    assert row["CLAIM_TOKEN"] is None
    assert row["NEXT_RETRY_AT"] is None

    print("[TEST] TIMEOUT_EXHAUSTED= True")
    print("[TEST] CLAIM_FIELDS_CLEARED= True")

    # 5. 旧 Token 不能确认成功
    assert confirm_outbox_sent(
        event_id, old_token
    ) is False

    print("[TEST] OLD_TOKEN_SENT_REJECTED= True")

    # 6. 旧 Token 不能确认失败
    assert confirm_outbox_failed(
        event_id, old_token
    ) is False

    print("[TEST] OLD_TOKEN_FAILED_REJECTED= True")

    # 7. EXHAUSTED 事件不能再次领取
    claimed_again = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert claimed_again == []
    assert read_event()["STATUS"] == "EXHAUSTED"

    print("[TEST] EXHAUSTED_NOT_RECLAIMED= True")
    print("[TEST] ALL PASS: Outbox timeout exhausted")

finally:
    # 仅清理本次测试记录
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
