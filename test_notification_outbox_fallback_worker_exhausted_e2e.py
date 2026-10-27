
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_worker import run_fallback_worker
from notification_outbox_fallback_dispatcher import (
    requeue_due_failed_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None
attempts = []


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


def always_fail(alert):
    attempts.append(alert["ALERT_ID"])
    raise RuntimeError("Simulated permanent failure")


def make_retry_due():
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

    for attempt in range(1, 4):
        result = run_fallback_worker(always_fail, limit=1)
        assert result["claimed"] == 1
        assert result["failed"] == 1

        stored = read_alert()
        assert stored["RETRY_COUNT"] == attempt

        if attempt < 3:
            assert stored["STATUS"] == "FAILED"
            assert stored["NEXT_RETRY_AT"] is not None
            make_retry_due()
            assert requeue_due_failed_fallback_alerts() == 1
            assert read_alert()["STATUS"] == "PENDING"
        else:
            assert stored["STATUS"] == "EXHAUSTED"
            assert stored["NEXT_RETRY_AT"] is None

        print(f"[TEST] ATTEMPT_{attempt}_STATE= True")

    assert requeue_due_failed_fallback_alerts() == 0
    print("[TEST] EXHAUSTED_NOT_REQUEUED= True")

    fourth = run_fallback_worker(always_fail, limit=1)
    assert fourth["claimed"] == 0
    assert attempts == [alert_id] * 3
    print("[TEST] FOURTH_ATTEMPT_BLOCKED= True")

    print("[TEST] ALL PASS: Fallback exhausted E2E")

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
