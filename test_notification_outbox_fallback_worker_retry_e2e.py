
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_worker import run_fallback_worker
from notification_outbox_fallback_dispatcher import (
    requeue_due_failed_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None
send_attempts = []


def read_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, RETRY_COUNT, NEXT_RETRY_AT
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


def fake_send(alert):
    send_attempts.append(alert["ALERT_ID"])
    if len(send_attempts) == 1:
        raise RuntimeError("Simulated first-attempt failure")


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

    # 第一次执行：模拟发送失败
    first = run_fallback_worker(fake_send, limit=1)
    assert first["failed"] == 1
    assert read_alert()["STATUS"] == "FAILED"
    assert read_alert()["RETRY_COUNT"] == 1
    print("[TEST] FIRST_ATTEMPT_FAILED= True")

    # 尚未到期，不应重新入队
    assert requeue_due_failed_fallback_alerts() == 0
    assert read_alert()["STATUS"] == "FAILED"
    print("[TEST] EARLY_REQUEUE_BLOCKED= True")

    # 只调整本测试记录的时间，避免等待 60 秒
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET NEXT_RETRY_AT = DATE_SUB(
                    CURRENT_TIMESTAMP(3),
                    INTERVAL 1 SECOND
                )
                WHERE ALERT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                  AND STATUS = 'FAILED'
                """,
                (alert_id, notification_type)
            )
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()

    # 到期后重新入队
    assert requeue_due_failed_fallback_alerts() == 1
    assert read_alert()["STATUS"] == "PENDING"
    print("[TEST] DUE_ALERT_REQUEUED= True")

    # 第二次执行：模拟发送成功
    second = run_fallback_worker(fake_send, limit=1)
    assert second["sent"] == 1
    assert second["confirmation_errors"] == 0

    final = read_alert()
    assert final["STATUS"] == "SENT"
    assert final["RETRY_COUNT"] == 2
    assert final["NEXT_RETRY_AT"] is None
    assert send_attempts == [alert_id, alert_id]

    print("[TEST] SECOND_ATTEMPT_SENT= True")
    print("[TEST] RETRY_COUNT_PRESERVED= True")
    print("[TEST] ALL PASS: Fallback worker retry E2E")

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
