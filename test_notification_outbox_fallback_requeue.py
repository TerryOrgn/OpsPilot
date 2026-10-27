
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    requeue_due_failed_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []


def read_alert(alert_id):
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
            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()


try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            test_cases = [
                (1, -60),  # 已到期
                (2, 120),  # 尚未到期
                (3, -60),  # 达到最大次数
            ]

            for retry_count, offset_seconds in test_cases:
                cursor.execute(
                    """
                    INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                        (
                            NOTIFICATION_TYPE,
                            OLD_STATUS,
                            NEW_STATUS,
                            STATUS,
                            RETRY_COUNT,
                            NEXT_RETRY_AT
                        )
                    VALUES (
                        %s,
                        'NORMAL',
                        'ACTION_REQUIRED',
                        'FAILED',
                        %s,
                        DATE_ADD(
                            CURRENT_TIMESTAMP(3),
                            INTERVAL %s SECOND
                        )
                    )
                    """,
                    (
                        notification_type,
                        retry_count,
                        offset_seconds,
                    )
                )
                created_ids.append(cursor.lastrowid)

        conn.commit()
    finally:
        conn.close()

    requeued_count = requeue_due_failed_fallback_alerts()

    assert requeued_count == 1
    print("[TEST] REQUEUED_COUNT= 1")

    # 已到期且未超过最大次数
    first = read_alert(created_ids[0])
    assert first["STATUS"] == "PENDING"
    assert first["RETRY_COUNT"] == 1
    assert first["NEXT_RETRY_AT"] is None
    print("[TEST] DUE_FAILED_REQUEUED= True")

    # 尚未到期
    second = read_alert(created_ids[1])
    assert second["STATUS"] == "FAILED"
    assert second["NEXT_RETRY_AT"] is not None
    print("[TEST] NOT_DUE_PROTECTED= True")

    # 已达到最大尝试次数
    third = read_alert(created_ids[2])
    assert third["STATUS"] == "FAILED"
    assert third["RETRY_COUNT"] == 3
    print("[TEST] MAX_ATTEMPTS_PROTECTED= True")

    print("[TEST] ALL PASS: Fallback retry requeue")

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
