
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    confirm_fallback_alert_failed,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []


def create_processing_alert(retry_count):
    claim_token = str(uuid4())
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
                (
                    notification_type,
                    claim_token,
                    retry_count,
                )
            )
            alert_id = cursor.lastrowid

        conn.commit()
        created_ids.append(alert_id)
        return alert_id, claim_token

    finally:
        conn.close()


def read_retry_status(alert_id):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
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
            columns = [
                item[0] for item in cursor.description
            ]

            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )

    finally:
        conn.close()


try:
    for retry_count, expected_delay in [
        (1, 60),
        (2, 120),
        (3, None),
    ]:
        alert_id, claim_token = create_processing_alert(
            retry_count
        )

        confirmed = confirm_fallback_alert_failed(
            alert_id,
            claim_token,
        )

        assert confirmed is True

        stored = read_retry_status(alert_id)


        expected_status = "EXHAUSTED" if retry_count >= 3 else "FAILED"
        assert stored["STATUS"] == expected_status

        assert stored["RETRY_COUNT"] == retry_count

        if expected_delay is None:
            assert stored["NEXT_RETRY_AT"] is None
            print("[TEST] THIRD_ATTEMPT_NO_RETRY= True")

        else:
            remaining = stored["REMAINING_SECONDS"]

            # 允许测试执行产生少量时间偏差
            assert expected_delay - 5 <= remaining <= expected_delay

            print(
                f"[TEST] RETRY_{retry_count}_DELAY= True "
                f"remaining_seconds={remaining}"
            )

    print("[TEST] ALL PASS: Fallback retry delay")

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
