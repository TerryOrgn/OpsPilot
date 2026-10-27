
from uuid import uuid4

from db import get_connection
from notification_outbox_monitor_state import (
    transition_outbox_monitor_state,
)

notification_type = "T_" + uuid4().hex[:20].upper()


def read_status():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXHAUSTED_STATUS
                FROM JOB_OUTBOX_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )

            row = cursor.fetchone()

            if isinstance(row, dict):
                return row["EXHAUSTED_STATUS"]

            return row[0] if row else None

    finally:
        conn.close()


try:
    # 1. 首次发现异常
    result = transition_outbox_monitor_state(
        notification_type,
        "ACTION_REQUIRED"
    )

    assert result["old_status"] == "NORMAL"
    assert result["new_status"] == "ACTION_REQUIRED"
    assert result["changed"] is True
    assert read_status() == "ACTION_REQUIRED"

    print("[TEST] FIRST_TRANSITION= True")

    # 2. 重复扫描，不应重复触发
    result = transition_outbox_monitor_state(
        notification_type,
        "ACTION_REQUIRED"
    )

    assert result["old_status"] == "ACTION_REQUIRED"
    assert result["changed"] is False
    assert read_status() == "ACTION_REQUIRED"

    print("[TEST] DUPLICATE_SUPPRESSED= True")

    # 3. 异常恢复
    result = transition_outbox_monitor_state(
        notification_type,
        "NORMAL"
    )

    assert result["old_status"] == "ACTION_REQUIRED"
    assert result["new_status"] == "NORMAL"
    assert result["changed"] is True
    assert read_status() == "NORMAL"

    print("[TEST] RECOVERY_TRANSITION= True")

    # 4. 重复恢复，不应重复触发
    result = transition_outbox_monitor_state(
        notification_type,
        "NORMAL"
    )

    assert result["old_status"] == "NORMAL"
    assert result["changed"] is False

    print("[TEST] DUPLICATE_RECOVERY_SUPPRESSED= True")

    # 5. 再次出现异常，允许重新触发
    result = transition_outbox_monitor_state(
        notification_type,
        "ACTION_REQUIRED"
    )

    assert result["old_status"] == "NORMAL"
    assert result["changed"] is True
    assert read_status() == "ACTION_REQUIRED"

    print("[TEST] RE_ALERT_AFTER_RECOVERY= True")
    print("[TEST] ALL PASS: Outbox monitor state")

finally:
    # 只清理本次测试记录
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM JOB_OUTBOX_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )

        conn.commit()
    finally:
        conn.close()
