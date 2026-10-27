
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    confirm_fallback_alert_failed,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []


def create_alert(retry_count):
    token = str(uuid4())
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (
                        NOTIFICATION_TYPE,
                        OLD_STATUS,
                        NEW_STATUS,
                        STATUS,
                        CLAIM_TOKEN,
                        CLAIMED_AT,
                        RETRY_COUNT
                    )
                VALUES (
                    %s,
                    'NORMAL',
                    'ACTION_REQUIRED',
                    'PROCESSING',
                    %s,
                    CURRENT_TIMESTAMP(3),
                    %s
                )
                """,
                (notification_type, token, retry_count)
            )
            alert_id = cursor.lastrowid
        conn.commit()
        created_ids.append(alert_id)
        return alert_id, token
    finally:
        conn.close()


def read_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
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
            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()


try:
    test_cases = [
        (1, "FAILED", 60),
        (2, "FAILED", 120),
        (3, "EXHAUSTED", None),
        (4, "EXHAUSTED", None),
    ]

    for retry_count, expected_status, expected_delay in test_cases:
        alert_id, token = create_alert(retry_count)

        result = confirm_fallback_alert_failed(
            alert_id, token
        )
        assert result is True

        stored = read_alert(alert_id)

        assert stored["STATUS"] == expected_status
        assert stored["CLAIM_TOKEN"] is None
        assert stored["CLAIMED_AT"] is None

        if expected_delay is None:
            assert stored["NEXT_RETRY_AT"] is None
        else:
            remaining = stored["REMAINING_SECONDS"]
            assert expected_delay - 5 <= remaining <= expected_delay

        print(
            f"[TEST] RETRY_{retry_count}_"
            f"{expected_status}= True"
        )

    print("[TEST] ALL PASS: Fallback exhausted transition")

finally:
    if created_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ",".join(
                    ["%s"] * len(created_ids)
                )
                cursor.execute(
                    f"""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID IN ({placeholders})
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (*created_ids, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
