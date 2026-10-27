
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    confirm_fallback_alert_sent,
)

notification_type = "T_" + uuid4().hex[:20].upper()
claim_token = str(uuid4())
alert_id = None


def read_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIM_TOKEN, CLAIMED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
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
    # 创建独立测试记录
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (
                        NOTIFICATION_TYPE,
                        OLD_STATUS,
                        NEW_STATUS,
                        STATUS,
                        CLAIM_TOKEN,
                        CLAIMED_AT,
                        RETRY_COUNT
                    )
                VALUES (
                    %s,
                    'NORMAL',
                    'ACTION_REQUIRED',
                    'PROCESSING',
                    %s,
                    CURRENT_TIMESTAMP(3),
                    1
                )
                """,
                (notification_type, claim_token)
            )
            alert_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 1. 错误 Token 不能确认
    wrong_result = confirm_fallback_alert_sent(
        alert_id, str(uuid4())
    )

    assert wrong_result is False
    assert read_alert()["STATUS"] == "PROCESSING"
    print("[TEST] WRONG_TOKEN_REJECTED= True")

    # 2. 正确 Token 确认成功
    success_result = confirm_fallback_alert_sent(
        alert_id, claim_token
    )

    assert success_result is True

    stored = read_alert()
    assert stored["STATUS"] == "SENT"
    assert stored["CLAIM_TOKEN"] is None
    assert stored["CLAIMED_AT"] is None

    print("[TEST] CORRECT_TOKEN_CONFIRMED= True")

    # 3. 重复确认无效
    duplicate_result = confirm_fallback_alert_sent(
        alert_id, claim_token
    )

    assert duplicate_result is False
    assert read_alert()["STATUS"] == "SENT"

    print("[TEST] DUPLICATE_CONFIRM_REJECTED= True")
    print("[TEST] ALL PASS: Fallback alert confirmation")

finally:
    if alert_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (alert_id, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
