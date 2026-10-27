
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_sent,
)

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

    # 2. 领取事件
    claimed = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(claimed) == 1
    assert claimed[0]["EVENT_ID"] == event_id

    correct_token = claimed[0]["CLAIM_TOKEN"]
    wrong_token = str(uuid4())

    # 3. 错误 Token 不允许确认
    wrong_result = confirm_outbox_sent(
        event_id, wrong_token
    )
    assert wrong_result is False

    # 4. 正确 Token 可以确认
    correct_result = confirm_outbox_sent(
        event_id, correct_token
    )
    assert correct_result is True

    # 5. 重复确认必须失败
    duplicate_result = confirm_outbox_sent(
        event_id, correct_token
    )
    assert duplicate_result is False

    # 6. 检查最终数据库状态
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIMED_AT, CLAIM_TOKEN
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
                stored_token = row["CLAIM_TOKEN"]
            else:
                status, claimed_at, stored_token = row
    finally:
        conn.close()

    assert status == "SENT"
    assert claimed_at is None
    assert stored_token is None

    print("[TEST] WRONG_TOKEN_REJECTED=", not wrong_result)
    print("[TEST] CORRECT_TOKEN_ACCEPTED=", correct_result)
    print("[TEST] DUPLICATE_REJECTED=", not duplicate_result)
    print("[TEST] FINAL_STATUS=", status)
    print("[TEST] TOKEN_CLEARED=", stored_token is None)
    print("[TEST] ALL PASS: Outbox sent confirmation")

finally:
    # 只删除本次创建的测试事件
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
