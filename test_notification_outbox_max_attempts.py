
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    recover_stale_outbox_events,
)

notification_type = "T_" + uuid4().hex[:20].upper()
event_ids = {}


def read_event(event_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, RETRY_COUNT,
                       CLAIMED_AT, CLAIM_TOKEN, NEXT_RETRY_AT
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (event_id, notification_type)
            )
            row = cursor.fetchone()
            columns = [item[0] for item in cursor.description]
            return row if isinstance(row, dict) else dict(zip(columns, row))
    finally:
        conn.close()


try:
    # 1. 创建两个已领取且超时的测试事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for name, retry_count in [
                ("BELOW_LIMIT", 2),
                ("AT_LIMIT", 3),
            ]:
                cursor.execute(
                    """
                    INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                        (
                            NOTIFICATION_TYPE, EVENT_TYPE, STATUS,
                            RETRY_COUNT, CLAIMED_AT, CLAIM_TOKEN
                        )
                    VALUES (
                        %s, 'DEAD_LETTER_DETECTED', 'PROCESSING',
                        %s,
                        CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE,
                        %s
                    )
                    """,
                    (notification_type, retry_count, str(uuid4()))
                )
                event_ids[name] = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 2. 执行超时恢复
    # 此函数扫描全表，仅在隔离的本地测试环境执行
    recover_stale_outbox_events(
        timeout_seconds=300,
        max_attempts=3
    )

    # 3. 未达到上限：恢复为 PENDING
    below = read_event(event_ids["BELOW_LIMIT"])

    assert below["STATUS"] == "PENDING"
    assert below["RETRY_COUNT"] == 2
    assert below["CLAIMED_AT"] is None
    assert below["CLAIM_TOKEN"] is None

    print("[TEST] BELOW_LIMIT_REQUEUED= True")

    # 4. 达到上限：终止为 FAILED
    at_limit = read_event(event_ids["AT_LIMIT"])

    assert at_limit["STATUS"] == "FAILED"
    assert at_limit["RETRY_COUNT"] == 3
    assert at_limit["CLAIMED_AT"] is None
    assert at_limit["CLAIM_TOKEN"] is None
    assert at_limit["NEXT_RETRY_AT"] is None

    print("[TEST] MAX_ATTEMPTS_STOPPED= True")

    # 5. 领取函数只能领取未达到上限的事件
    claimed = claim_pending_outbox_events(
        limit=2,
        notification_type=notification_type
    )

    assert len(claimed) == 1
    assert claimed[0]["EVENT_ID"] == event_ids["BELOW_LIMIT"]

    below = read_event(event_ids["BELOW_LIMIT"])
    assert below["STATUS"] == "PROCESSING"
    assert below["RETRY_COUNT"] == 3

    at_limit = read_event(event_ids["AT_LIMIT"])
    assert at_limit["STATUS"] == "FAILED"

    print("[TEST] MAX_ATTEMPTS_NOT_RECLAIMED= True")
    print("[TEST] ALL PASS: Outbox max attempts")

finally:
    # 仅清理本次测试事件
    if event_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE NOTIFICATION_TYPE = %s
                    """,
                    (notification_type,)
                )
            conn.commit()
        finally:
            conn.close()
