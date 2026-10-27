
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    recover_stale_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []


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
                    RETRY_COUNT,
                    NEXT_RETRY_AT
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
            # 避免修改已有的超时 PROCESSING 记录
            cursor.execute(
                """
                SELECT COUNT(*) AS TOTAL
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE STATUS = 'PROCESSING'
                """
            )
            row = cursor.fetchone()
            existing = (
                row["TOTAL"] if isinstance(row, dict)
                else row[0]
            )
            assert existing == 0, (
                "Existing PROCESSING alerts found. "
                "Use an isolated test database."
            )

            test_cases = [
                (1, -600),  # 超时，允许恢复
                (3, -600),  # 超时，达到最大次数
                (1, -30),   # 未超时
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
                        DATE_ADD(
                            CURRENT_TIMESTAMP(3),
                            INTERVAL %s SECOND
                        ),
                        %s
                    )
                    """,
                    (
                        notification_type,
                        str(uuid4()),
                        offset_seconds,
                        retry_count,
                    )
                )
                created_ids.append(cursor.lastrowid)

        conn.commit()
    finally:
        conn.close()

    recovered_count = recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )

    assert recovered_count == 2
    print("[TEST] RECOVERED_COUNT= 2")

    # 1. 超时且未达到最大次数
    first = read_alert(created_ids[0])
    assert first["STATUS"] == "PENDING"
    assert first["CLAIM_TOKEN"] is None
    assert first["CLAIMED_AT"] is None
    assert first["RETRY_COUNT"] == 1
    print("[TEST] STALE_REQUEUED= True")

    # 2. 超时且达到最大次数
    second = read_alert(created_ids[1])
    assert second["STATUS"] == "EXHAUSTED"
    assert second["CLAIM_TOKEN"] is None
    assert second["CLAIMED_AT"] is None
    assert second["NEXT_RETRY_AT"] is None
    print("[TEST] STALE_EXHAUSTED= True")

    # 3. 未超时的记录不受影响
    third = read_alert(created_ids[2])
    assert third["STATUS"] == "PROCESSING"
    assert third["CLAIM_TOKEN"] is not None
    assert third["CLAIMED_AT"] is not None
    print("[TEST] ACTIVE_CLAIM_PROTECTED= True")

    print("[TEST] ALL PASS: Fallback stale recovery")

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
