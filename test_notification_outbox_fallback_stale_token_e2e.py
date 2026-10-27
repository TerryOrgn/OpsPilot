
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    recover_stale_fallback_alerts,
    confirm_fallback_alert_sent,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None


def read_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIM_TOKEN, RETRY_COUNT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            columns = [c[0] for c in cursor.description]
            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()


try:
    # 准备隔离测试数据
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
            assert count == 0, (
                "Use an empty isolated test database"
            )

            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (
                        NOTIFICATION_TYPE,
                        OLD_STATUS,
                        NEW_STATUS,
                        STATUS
                    )
                VALUES (
                    %s, 'NORMAL',
                    'ACTION_REQUIRED', 'PENDING'
                )
                """,
                (notification_type,)
            )
            alert_id = cursor.lastrowid

        conn.commit()
    finally:
        conn.close()

    # Worker A 第一次领取
    claimed_a = claim_pending_fallback_alerts(limit=1)
    assert len(claimed_a) == 1
    assert claimed_a[0]["ALERT_ID"] == alert_id

    token_a = claimed_a[0]["CLAIM_TOKEN"]
    assert token_a
    print("[TEST] WORKER_A_CLAIMED= True")

    # 仅修改测试记录，模拟 A 已超时
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
                  AND NOTIFICATION_TYPE = %s
                  AND STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
                """,
                (alert_id, notification_type, token_a)
            )
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    # 恢复超时领取
    recovered = recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )
    assert recovered == 1
    assert read_alert()["STATUS"] == "PENDING"
    print("[TEST] WORKER_A_EXPIRED= True")

    # Worker B 重新领取
    claimed_b = claim_pending_fallback_alerts(limit=1)
    assert len(claimed_b) == 1
    assert claimed_b[0]["ALERT_ID"] == alert_id

    token_b = claimed_b[0]["CLAIM_TOKEN"]
    assert token_b != token_a
    assert read_alert()["RETRY_COUNT"] == 2
    print("[TEST] WORKER_B_RECLAIMED= True")

    # A 使用旧 Token 确认：必须失败
    old_result = confirm_fallback_alert_sent(
        alert_id, token_a
    )
    assert old_result is False

    current = read_alert()
    assert current["STATUS"] == "PROCESSING"
    assert current["CLAIM_TOKEN"] == token_b
    print("[TEST] STALE_TOKEN_REJECTED= True")

    # B 使用新 Token 确认：必须成功
    new_result = confirm_fallback_alert_sent(
        alert_id, token_b
    )
    assert new_result is True

    final = read_alert()
    assert final["STATUS"] == "SENT"
    assert final["CLAIM_TOKEN"] is None
    assert final["RETRY_COUNT"] == 2
    print("[TEST] CURRENT_TOKEN_ACCEPTED= True")

    print("[TEST] ALL PASS: Fallback stale token E2E")

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
