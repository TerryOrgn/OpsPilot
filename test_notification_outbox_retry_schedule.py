
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_failed,
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
                    NEXT_RETRY_AT,
                    TIMESTAMPDIFF(
                        SECOND,
                        CURRENT_TIMESTAMP(3),
                        NEXT_RETRY_AT
                    ) AS SECONDS_UNTIL_RETRY
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
    claimed = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(claimed) == 1
    assert claimed[0]["EVENT_ID"] == event_id

    correct_token = claimed[0]["CLAIM_TOKEN"]

    row = read_event()
    assert row["STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 1
    assert row["NEXT_RETRY_AT"] is None

    # 3. 错误 Token 不得修改状态或重试时间
    wrong_result = confirm_outbox_failed(
        event_id,
        str(uuid4())
    )

    assert wrong_result is False

    row = read_event()
    assert row["STATUS"] == "PROCESSING"
    assert row["NEXT_RETRY_AT"] is None

    print("[TEST] WRONG_TOKEN_REJECTED= True")

    # 4. 正确 Token 确认失败
    correct_result = confirm_outbox_failed(
        event_id,
        correct_token
    )

    assert correct_result is True

    row = read_event()

    assert row["STATUS"] == "FAILED"
    assert row["RETRY_COUNT"] == 1
    assert row["NEXT_RETRY_AT"] is not None

    seconds = row["SECONDS_UNTIL_RETRY"]

    # 允许少量执行时间误差
    assert 55 <= seconds <= 60, (
        f"Unexpected retry delay: {seconds}"
    )

    print("[TEST] FINAL_STATUS=", row["STATUS"])
    print("[TEST] RETRY_COUNT=", row["RETRY_COUNT"])
    print("[TEST] NEXT_RETRY_AT=", row["NEXT_RETRY_AT"])
    print("[TEST] SECONDS_UNTIL_RETRY=", seconds)
    print("[TEST] ALL PASS: Outbox retry schedule")

finally:
    # 仅清理本次测试事件
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
