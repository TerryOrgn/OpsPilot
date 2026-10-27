
from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    confirm_fallback_alert_sent,
    recover_stale_fallback_alerts,
)
from webhook_idempotency_processor import process_webhook_event


alert_id = None


def get_fallback_status(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
            return cursor.fetchone()["STATUS"]
    finally:
        conn.close()


def get_business_count(key):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS TOTAL
                FROM WEBHOOK_BUSINESS_TEST
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
            return cursor.fetchone()["TOTAL"]
    finally:
        conn.close()


try:
    # 1. 创建 Fallback 告警
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

    key = str(alert_id)

    payload = {
        "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
        "alert_id": alert_id,
        "notification_type": "OUTBOX_EXHAUSTED",
        "old_status": "NORMAL",
        "new_status": "ACTION_REQUIRED",
    }

    # 2. 第一次领取和投递
    first_claim = claim_pending_fallback_alerts(limit=1)
    assert len(first_claim) == 1
    assert first_claim[0]["ALERT_ID"] == alert_id

    first_result = process_webhook_event(key, payload)
    assert first_result == "PROCESSED", first_result
    assert get_business_count(key) == 1

    print("[TEST] FIRST_DELIVERY_PROCESSED= True")

    # 3. 模拟确认丢失：不调用 confirm_sent
    assert get_fallback_status(alert_id) == "PROCESSING"

    print("[TEST] SENDER_CONFIRMATION_LOST= True")

    # 4. 模拟 Claim 超时
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

    recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )

    assert get_fallback_status(alert_id) == "PENDING"

    print("[TEST] STALE_ALERT_RECOVERED= True")

    # 5. 第二次领取
    second_claim = claim_pending_fallback_alerts(limit=1)
    assert len(second_claim) == 1
    assert second_claim[0]["ALERT_ID"] == alert_id

    assert (
        second_claim[0]["CLAIM_TOKEN"]
        != first_claim[0]["CLAIM_TOKEN"]
    )

    # 6. 第二次投递相同事件
    second_result = process_webhook_event(key, payload)
    assert second_result == "DUPLICATE", second_result

    print("[TEST] SECOND_DELIVERY_DUPLICATE= True")

    # 7. 发送方成功确认
    confirmed = confirm_fallback_alert_sent(
        alert_id,
        second_claim[0]["CLAIM_TOKEN"],
    )

    assert confirmed is True
    assert get_fallback_status(alert_id) == "SENT"

    print("[TEST] FINAL_STATUS_SENT= True")

    # 8. 验证业务只执行一次
    assert get_business_count(key) == 1

    print("[TEST] BUSINESS_EXECUTED_ONCE= True")
    print("[TEST] ALL PASS: Recovery idempotency")

finally:
    if alert_id is not None:
        key = str(alert_id)
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM WEBHOOK_BUSINESS_TEST
                    WHERE IDEMPOTENCY_KEY = %s
                """, (key,))

                cursor.execute("""
                    DELETE FROM WEBHOOK_IDEMPOTENCY
                    WHERE IDEMPOTENCY_KEY = %s
                """, (key,))

                cursor.execute("""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                """, (alert_id,))

            conn.commit()
        finally:
            conn.close()
