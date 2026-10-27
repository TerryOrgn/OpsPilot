
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None


def fake_send(alert):
    raise RuntimeError("Simulated delivery failure")


try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM JOB_OUTBOX_FALLBACK_ALERT
                """
            )
            row = cursor.fetchone()
            count = (
                next(iter(row.values()))
                if isinstance(row, dict)
                else row[0]
            )
            assert count == 0, (
                "Use an empty, isolated test database."
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
                    %s,
                    'NORMAL',
                    'ACTION_REQUIRED',
                    'PENDING'
                )
                """,
                (notification_type,)
            )
            alert_id = cursor.lastrowid

        conn.commit()
    finally:
        conn.close()

    result = run_fallback_worker(
        send_alert=fake_send,
        limit=1,
    )

    assert result == {
        "claimed": 1,
        "sent": 0,
        "failed": 1,
        "confirmation_errors": 0,
    }
    print("[TEST] WORKER_FAILURE_COUNT= True")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    CLAIMED_AT,
                    NEXT_RETRY_AT,
                    TIMESTAMPDIFF(
                        SECOND,
                        CURRENT_TIMESTAMP(3),
                        NEXT_RETRY_AT
                    ) AS REMAINING_SECONDS
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            columns = [c[0] for c in cursor.description]
            stored = (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()

    assert stored["STATUS"] == "FAILED"
    assert stored["RETRY_COUNT"] == 1
    print("[TEST] MYSQL_STATUS_FAILED= True")

    assert stored["CLAIM_TOKEN"] is None
    assert stored["CLAIMED_AT"] is None
    print("[TEST] CLAIM_CLEARED= True")

    remaining = stored["REMAINING_SECONDS"]
    assert remaining is not None
    assert 55 <= remaining <= 60
    print("[TEST] RETRY_DELAY_60_SECONDS= True")

    print("[TEST] ALL PASS: Fallback worker MySQL failure")

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
