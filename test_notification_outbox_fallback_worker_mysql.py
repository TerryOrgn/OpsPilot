
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None
delivered = []


def fake_send(alert):
    delivered.append(alert["ALERT_ID"])


def read_status(alert_id):
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
            return cursor.fetchone()
    finally:
        conn.close()


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
                "Fallback alert table is not empty. "
                "Stop other workers and use an isolated database."
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
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 0,
    }
    print("[TEST] WORKER_RESULT= True")

    assert delivered == [alert_id]
    print("[TEST] ALERT_DELIVERED= True")

    row = read_status(alert_id)

    if isinstance(row, dict):
        status = row["STATUS"]
        claim_token = row["CLAIM_TOKEN"]
        claimed_at = row["CLAIMED_AT"]
    else:
        status, claim_token, claimed_at = row

    assert status == "SENT"
    print("[TEST] MYSQL_STATUS_SENT= True")

    assert claim_token is None
    assert claimed_at is None
    print("[TEST] CLAIM_CLEARED= True")

    print("[TEST] ALL PASS: Fallback worker MySQL")

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
