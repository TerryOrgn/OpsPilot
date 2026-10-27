
from uuid import uuid4

from db import get_connection
from notification_monitor_state import transition_dead_letter_state

notification_type = "T_" + uuid4().hex[:20].upper()

try:
    # 首次建立基线
    assert transition_dead_letter_state(
        notification_type, "NORMAL"
    ) is None

    # 第一次发生异常
    event1 = transition_dead_letter_state(
        notification_type, "ACTION_REQUIRED"
    )

    # 重复检测相同异常
    event2 = transition_dead_letter_state(
        notification_type, "ACTION_REQUIRED"
    )
    event3 = transition_dead_letter_state(
        notification_type, "ACTION_REQUIRED"
    )

    assert event1 == "DEAD_LETTER_DETECTED"
    assert event2 is None
    assert event3 is None

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )
            row = cursor.fetchone()
            count = (
                next(iter(row.values()))
                if isinstance(row, dict)
                else row[0]
            )
    finally:
        conn.close()

    assert count == 1

    print("[TEST] FIRST_EVENT=", event1)
    print("[TEST] SECOND_EVENT=", event2)
    print("[TEST] THIRD_EVENT=", event3)
    print("[TEST] OUTBOX_COUNT=", count)
    print("[TEST] ALL PASS: Outbox event deduplication")

finally:
    # 清理本次测试记录
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
            cursor.execute(
                """
                DELETE FROM JOB_NOTIFICATION_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )
        conn.commit()
    finally:
        conn.close()
