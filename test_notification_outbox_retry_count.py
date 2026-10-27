
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    recover_stale_outbox_events,
)

notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None


def read_event():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, RETRY_COUNT, CLAIM_TOKEN
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )
            row = cursor.fetchone()

            if isinstance(row, dict):
                return row

            return dict(zip(
                ["STATUS", "RETRY_COUNT", "CLAIM_TOKEN"],
                row
            ))
    finally:
        conn.close()


try:
    # 1. 创建独立测试事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                    (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                VALUES (%s, %s, 'PENDING')
                """,
                (notification_type, "DEAD_LETTER_DETECTED")
            )
            event_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    assert read_event()["RETRY_COUNT"] == 0
    print("[TEST] INITIAL_RETRY_COUNT= 0")

    # 2. 第一次领取
    first = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(first) == 1
    assert first[0]["EVENT_ID"] == event_id

    first_token = first[0]["CLAIM_TOKEN"]
    row = read_event()

    assert row["STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] == first_token

    print("[TEST] FIRST_CLAIM_RETRY_COUNT= 1")

    # 3. 模拟10分钟前领取
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )
        conn.commit()
    finally:
        conn.close()

    # 注意：恢复函数扫描全表，只在隔离的本地测试环境运行
    recover_stale_outbox_events(timeout_seconds=300)

    row = read_event()
    assert row["STATUS"] == "PENDING"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None

    print("[TEST] RECOVERY_RETRY_COUNT= 1")

    # 4. 第二次领取
    second = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(second) == 1
    assert second[0]["EVENT_ID"] == event_id

    row = read_event()

    assert row["STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 2
    assert row["CLAIM_TOKEN"] == second[0]["CLAIM_TOKEN"]
    assert row["CLAIM_TOKEN"] != first_token

    print("[TEST] SECOND_CLAIM_RETRY_COUNT= 2")
    print("[TEST] NEW_TOKEN_GENERATED= True")
    print("[TEST] ALL PASS: Outbox retry count")

finally:
    # 仅清理本次测试事件
    if event_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE EVENT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (event_id, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
