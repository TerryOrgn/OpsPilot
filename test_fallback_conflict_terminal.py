from db import get_connection

from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    confirm_fallback_alert_conflict,
)


alert_id = None

try:
    # 创建测试告警
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS,
                     NEW_STATUS, STATUS)
                VALUES (%s, %s, %s, 'PENDING')
            """, (
                "OUTBOX_EXHAUSTED",
                "NORMAL",
                "ACTION_REQUIRED",
            ))

            alert_id = cursor.lastrowid

        conn.commit()

    finally:
        conn.close()

    # 领取告警
    claimed = claim_pending_fallback_alerts(limit=1)

    assert len(claimed) == 1
    assert claimed[0]["ALERT_ID"] == alert_id

    token = claimed[0]["CLAIM_TOKEN"]

    # 使用正确 Token 确认冲突
    assert confirm_fallback_alert_conflict(
        alert_id, token
    ) is True

    print("[TEST] CONFLICT_CONFIRMED= True")

    # 检查最终数据库状态
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, CLAIM_TOKEN,
                       CLAIMED_AT, NEXT_RETRY_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))

            row = cursor.fetchone()

    finally:
        conn.close()

    assert row["STATUS"] == "EXHAUSTED"
    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None
    assert row["NEXT_RETRY_AT"] is None

    print("[TEST] CONFLICT_TERMINAL_STATE= True")

    # 旧 Token 不得再次确认
    assert confirm_fallback_alert_conflict(
        alert_id, token
    ) is False

    print("[TEST] STALE_TOKEN_REJECTED= True")

    print("[TEST] ALL PASS: Fallback conflict terminal")

finally:
    if alert_id is not None:
        conn = get_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                """, (alert_id,))

            conn.commit()

        finally:
            conn.close()