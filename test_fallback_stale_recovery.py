
from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    recover_stale_fallback_alerts,
)

alert_id = None


def get_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, CLAIM_TOKEN, CLAIMED_AT,
                       RETRY_COUNT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            return cursor.fetchone()
    finally:
        conn.close()


try:
    # 1. 创建测试告警
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

    # 2. 领取告警
    claimed = claim_pending_fallback_alerts(limit=1)

    assert len(claimed) == 1, claimed
    assert claimed[0]["ALERT_ID"] == alert_id, claimed

    old_token = claimed[0]["CLAIM_TOKEN"]
    row = get_alert(alert_id)

    assert row["STATUS"] == "PROCESSING"
    assert row["CLAIM_TOKEN"] == old_token

    print("[TEST] ALERT_CLAIMED= True")

    # 3. 模拟领取时间已经超过 5 分钟
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
            """, (alert_id,))
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    # 4. 执行超时恢复
    recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )

    row = get_alert(alert_id)

    assert row["STATUS"] == "PENDING", row
    assert row["CLAIM_TOKEN"] is None, row
    assert row["CLAIMED_AT"] is None, row

    print("[TEST] STALE_ALERT_RECOVERED= True")

    # 5. 验证能够再次领取
    claimed_again = claim_pending_fallback_alerts(limit=1)

    assert len(claimed_again) == 1, claimed_again
    assert claimed_again[0]["ALERT_ID"] == alert_id

    new_token = claimed_again[0]["CLAIM_TOKEN"]

    assert new_token != old_token
    assert get_alert(alert_id)["STATUS"] == "PROCESSING"

    print("[TEST] ALERT_RECLAIMED= True")
    print("[TEST] NEW_CLAIM_TOKEN= True")
    print("[TEST] ALL PASS: Fallback stale recovery")

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
