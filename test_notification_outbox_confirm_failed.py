
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_failed,
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

    # 3. 错误 Token 必须被拒绝
    wrong_result = confirm_outbox_failed(
        event_id, wrong_token
    )
    assert wrong_result is False

    # 4. 错误 Token 不得修改当前领取状态
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIM_TOKEN
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (event_id,)
            )
            row = cursor.fetchone()
            if isinstance(row, dict):
                assert row["STATUS"] == "PROCESSING"
                assert row["CLAIM_TOKEN"] == correct_token
            else:
                assert row == ("PROCESSING", correct_token)
    finally:
        conn.close()

    # 5. 正确 Token 可以确认失败
    correct_result = confirm_outbox_failed(
        event_id, correct_token
    )
    assert correct_result is True

    # 6. 重复确认必须被拒绝
    duplicate_result = confirm_outbox_failed(
        event_id, correct_token
    )
    assert duplicate_result is False

    # 7. 验证最终数据库状态
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIMED_AT, CLAIM_TOKEN
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (event_id,)
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

    assert status == "FAILED"
    assert claimed_at is None
    assert stored_token is None

    print("[TEST] WRONG_TOKEN_REJECTED= True")
    print("[TEST] WRONG_TOKEN_STATE_UNCHANGED= True")
    print("[TEST] CORRECT_TOKEN_ACCEPTED=", correct_result)
    print("[TEST] DUPLICATE_REJECTED=", not duplicate_result)
    print("[TEST] FINAL_STATUS=", status)
    print("[TEST] CLAIM_FIELDS_CLEARED= True")
    print("[TEST] ALL PASS: Outbox failed confirmation")

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
