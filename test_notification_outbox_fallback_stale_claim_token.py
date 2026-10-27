
from db import get_connection

from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    recover_stale_fallback_alerts,
    confirm_fallback_alert_sent,
    confirm_fallback_alert_failed,
)


def get_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, CLAIMED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            return cursor.fetchone()
    finally:
        conn.close()


def update_claimed_at(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 600 SECOND
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
            """, (alert_id,))
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()


alert_id = None

try:
    # 1. 创建测试告警
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS, NEW_STATUS, STATUS)
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

    # 2. Worker A 领取
    claimed_a = claim_pending_fallback_alerts(limit=1)

    assert len(claimed_a) == 1
    assert claimed_a[0]["ALERT_ID"] == alert_id

    token_a = claimed_a[0]["CLAIM_TOKEN"]
    assert token_a

    print("[TEST] WORKER_A_CLAIMED= True")

    # 3. 模拟 Worker A 超时
    update_claimed_at(alert_id)

    recovered = recover_stale_fallback_alerts(
        timeout_seconds=300
    )

    assert recovered == 1

    after_recovery = get_alert(alert_id)
    assert after_recovery["STATUS"] == "PENDING"
    assert after_recovery["CLAIM_TOKEN"] is None

    print("[TEST] STALE_CLAIM_RECOVERED= True")

    # 4. Worker B 重新领取
    claimed_b = claim_pending_fallback_alerts(limit=1)

    assert len(claimed_b) == 1
    assert claimed_b[0]["ALERT_ID"] == alert_id

    token_b = claimed_b[0]["CLAIM_TOKEN"]

    assert token_b
    assert token_a != token_b

    print("[TEST] WORKER_B_RECLAIMED= True")

    # 5. Worker A 使用旧 Token 确认成功
    stale_sent = confirm_fallback_alert_sent(
        alert_id,
        token_a,
    )

    assert not stale_sent

    # 6. Worker A 使用旧 Token 确认失败
    stale_failed = confirm_fallback_alert_failed(
        alert_id,
        token_a,
    )

    assert not stale_failed

    # 7. 确认 Worker B 的领取权未被破坏
    current = get_alert(alert_id)

    assert current["STATUS"] == "PROCESSING"
    assert current["CLAIM_TOKEN"] == token_b
    assert current["RETRY_COUNT"] == 2

    print("[TEST] STALE_TOKEN_REJECTED= True")
    print("[TEST] NEW_CLAIM_PROTECTED= True")

    # 8. Worker B 正常确认成功
    confirmed = confirm_fallback_alert_sent(
        alert_id,
        token_b,
    )

    assert confirmed

    final = get_alert(alert_id)

    assert final["STATUS"] == "SENT"
    assert final["RETRY_COUNT"] == 2
    assert final["CLAIM_TOKEN"] is None
    assert final["CLAIMED_AT"] is None

    print("[TEST] WORKER_B_CONFIRMED= True")
    print("[TEST] ALL PASS: Stale claim token protection")

finally:
    if alert_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                """, (
                    alert_id,
                    "OUTBOX_EXHAUSTED",
                ))
            conn.commit()
        finally:
            conn.close()
