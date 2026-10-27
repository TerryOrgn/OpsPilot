
from uuid import uuid4

from db import get_connection
from notification_monitor_state import (
    transition_dead_letter_state,
    get_dead_letter_state,
)

# 每次运行使用独立测试类型，避免影响已有数据
notification_type = "T_" + uuid4().hex[:20].upper()

conn = get_connection()

try:
    # 首次观察建立 NORMAL 基线，不产生事件
    event1 = transition_dead_letter_state(
        notification_type, "NORMAL"
    )
    assert event1 is None

    # 状态变化：应该同时更新监控状态并写入 Outbox
    event2 = transition_dead_letter_state(
        notification_type, "ACTION_REQUIRED"
    )
    assert event2 == "DEAD_LETTER_DETECTED"

    assert get_dead_letter_state(notification_type) == "ACTION_REQUIRED"

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EVENT_TYPE, STATUS
            FROM JOB_MONITOR_EVENT_OUTBOX
            WHERE NOTIFICATION_TYPE = %s
            """,
            (notification_type,)
        )
        rows = cursor.fetchall()

    assert len(rows) == 1
    row = rows[0]

    if isinstance(row, dict):
        event_type = row["EVENT_TYPE"]
        status = row["STATUS"]
    else:
        event_type, status = row

    assert event_type == "DEAD_LETTER_DETECTED"
    assert status == "PENDING"

    print("[TEST] EVENT=", event2)
    print("[TEST] OUTBOX_COUNT=", len(rows))
    print("[TEST] OUTBOX_STATUS=", status)
    print("[TEST] ALL PASS: Atomic success")

finally:
    # 仅清理本次测试创建的两张表记录
    try:
        conn.rollback()
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
