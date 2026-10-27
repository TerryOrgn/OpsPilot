
from uuid import uuid4

from db import get_connection
from notification_outbox import (
    claim_pending_outbox_events,
    confirm_outbox_sent,
    recover_stale_outbox_events,
)

notification_type = "T_" + uuid4().hex[:20].upper()
event_ids = []

def read_event(event_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIMED_AT, CLAIM_TOKEN
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (event_id,)
            )
            row = cursor.fetchone()
            if isinstance(row, dict):
                return row
            return dict(zip(
                ["STATUS", "CLAIMED_AT", "CLAIM_TOKEN"], row
            ))
    finally:
        conn.close()

try:
    # 1. 创建两个独立事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for _ in range(2):
                cursor.execute(
                    """
                    INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                        (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                    VALUES (%s, %s, 'PENDING')
                    """,
                    (notification_type, "DEAD_LETTER_DETECTED")
                )
                event_ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # 2. 领取两个事件
    claimed = claim_pending_outbox_events(
        limit=2,
        notification_type=notification_type
    )
    assert len(claimed) == 2

    tokens = {
        event["EVENT_ID"]: event["CLAIM_TOKEN"]
        for event in claimed
    }

    stale_id, fresh_id = event_ids
    old_token = tokens[stale_id]

    # 3. 仅将第一个事件模拟为10分钟前领取
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE
                WHERE EVENT_ID = %s
                """,
                (stale_id,)
            )
        conn.commit()
    finally:
        conn.close()

    # 4. 恢复超过5分钟的事件
    # 注意：该函数会扫描全表，返回数量可能包含其他测试记录
    recovered_count = recover_stale_outbox_events(
        timeout_seconds=300
    )

    stale_row = read_event(stale_id)
    fresh_row = read_event(fresh_id)

    assert stale_row["STATUS"] == "PENDING"
    assert stale_row["CLAIMED_AT"] is None
    assert stale_row["CLAIM_TOKEN"] is None

    assert fresh_row["STATUS"] == "PROCESSING"
    assert fresh_row["CLAIM_TOKEN"] == tokens[fresh_id]

    print("[TEST] STALE_RECOVERED= True")
    print("[TEST] FRESH_UNCHANGED= True")

    # 5. 旧 Token 无法确认
    assert confirm_outbox_sent(stale_id, old_token) is False
    print("[TEST] OLD_TOKEN_REJECTED= True")

    # 6. 重新领取恢复的事件
    reclaimed = claim_pending_outbox_events(
        limit=1,
        notification_type=notification_type
    )

    assert len(reclaimed) == 1
    assert reclaimed[0]["EVENT_ID"] == stale_id
    assert reclaimed[0]["CLAIM_TOKEN"] != old_token

    print("[TEST] NEW_TOKEN_GENERATED= True")
    print("[TEST] ALL PASS: Outbox stale recovery")

finally:
    # 只清理本次测试创建的事件
    if event_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ",".join(["%s"] * len(event_ids))
                cursor.execute(
                    f"""
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE EVENT_ID IN ({placeholders})
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (*event_ids, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
