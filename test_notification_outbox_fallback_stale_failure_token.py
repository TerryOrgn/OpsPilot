
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    recover_stale_fallback_alerts,
    confirm_fallback_alert_failed,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None


def read_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIM_TOKEN, RETRY_COUNT,
                       NEXT_RETRY_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            columns = [c[0] for c in cursor.description]
            return row if isinstance(row, dict) else dict(zip(columns, row))
    finally:
        conn.close()


try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM JOB_OUTBOX_FALLBACK_ALERT"
            )
            row = cursor.fetchone()
            count = (
                next(iter(row.values()))
                if isinstance(row, dict)
                else row[0]
            )
            assert count == 0, "Use an empty isolated test database"

            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS, NEW_STATUS, STATUS)
                VALUES (%s, 'NORMAL', 'ACTION_REQUIRED', 'PENDING')
                """,
                (notification_type,)
            )
            alert_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Worker A 领取
    claimed_a = claim_pending_fallback_alerts(limit=1)
    assert len(claimed_a) == 1
    assert claimed_a[0]["ALERT_ID"] == alert_id
    token_a = claimed_a[0]["CLAIM_TOKEN"]

    # 模拟 A 超时
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET CLAIMED_AT = DATE_SUB(
                    CURRENT_TIMESTAMP(3),
                    INTERVAL 600 SECOND
                )
                WHERE ALERT_ID = %s
                  AND CLAIM_TOKEN = %s
                  AND STATUS = 'PROCESSING'
                """,
                (alert_id, token_a)
            )
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    assert recover_stale_fallback_alerts() == 1

    # Worker B 重新领取
    claimed_b = claim_pending_fallback_alerts(limit=1)
    assert len(claimed_b) == 1
    token_b = claimed_b[0]["CLAIM_TOKEN"]
    assert token_b != token_a

    # A 使用旧 Token 确认失败
    stale_result = confirm_fallback_alert_failed(
        alert_id, token_a
    )
    assert stale_result is False

    current = read_alert()
    assert current["STATUS"] == "PROCESSING"
    assert current["CLAIM_TOKEN"] == token_b
    assert current["RETRY_COUNT"] == 2
    assert current["NEXT_RETRY_AT"] is None

    print("[TEST] STALE_FAILURE_TOKEN_REJECTED= True")
    print("[TEST] NEW_CLAIM_PROTECTED= True")

    # B 使用新 Token 确认失败
    valid_result = confirm_fallback_alert_failed(
        alert_id, token_b
    )
    assert valid_result is True

    final = read_alert()
    assert final["STATUS"] == "FAILED"
    assert final["CLAIM_TOKEN"] is None
    assert final["RETRY_COUNT"] == 2
    assert final["NEXT_RETRY_AT"] is not None

    print("[TEST] CURRENT_FAILURE_TOKEN_ACCEPTED= True")
    print("[TEST] ALL PASS: Fallback stale failure token")

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
