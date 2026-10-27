
from uuid import uuid4
from unittest.mock import patch

from db import get_connection
from notification_outbox_monitor_state import (
    transition_outbox_monitor_state,
)

notification_type = "T_" + uuid4().hex[:20].upper()


def read_state():
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
            if row is None:
                return None
            return (
                row["EXHAUSTED_STATUS"]
                if isinstance(row, dict)
                else row[0]
            )
    finally:
        conn.close()


def read_alerts():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT OLD_STATUS, NEW_STATUS, STATUS
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE NOTIFICATION_TYPE = %s
                ORDER BY ALERT_ID
                """,
                (notification_type,)
            )
            rows = cursor.fetchall()
            columns = [c[0] for c in cursor.description]
            return [
                row if isinstance(row, dict)
                else dict(zip(columns, row))
                for row in rows
            ]
    finally:
        conn.close()


try:
    # 1. 首次异常：状态和告警同时提交
    result = transition_outbox_monitor_state(
        notification_type, "ACTION_REQUIRED"
    )

    assert result["changed"] is True
    assert read_state() == "ACTION_REQUIRED"

    alerts = read_alerts()
    assert len(alerts) == 1
    assert alerts[0] == {
        "OLD_STATUS": "NORMAL",
        "NEW_STATUS": "ACTION_REQUIRED",
        "STATUS": "PENDING",
    }

    print("[TEST] ATOMIC_COMMIT= True")

    # 2. 重复异常：不新增告警
    result = transition_outbox_monitor_state(
        notification_type, "ACTION_REQUIRED"
    )

    assert result["changed"] is False
    assert len(read_alerts()) == 1

    print("[TEST] DUPLICATE_SUPPRESSED= True")

    # 3. 模拟告警插入失败
    # 临时将合法状态集合改为非法状态，
    # 触发 MySQL CHECK 约束失败
    with patch(
        "notification_outbox_monitor_state.VALID_STATUSES",
        {"NORMAL", "ACTION_REQUIRED", "INVALID"}
    ):
        try:
            transition_outbox_monitor_state(
                notification_type, "INVALID"
            )
        except Exception:
            pass
        else:
            raise AssertionError(
                "Expected database constraint failure"
            )

    # 4. 确认 UPDATE 也被回滚
    assert read_state() == "ACTION_REQUIRED"
    assert len(read_alerts()) == 1

    print("[TEST] TRANSACTION_ROLLBACK= True")

    # 5. 恢复状态：产生第二条告警
    result = transition_outbox_monitor_state(
        notification_type, "NORMAL"
    )

    assert result["changed"] is True
    assert read_state() == "NORMAL"

    alerts = read_alerts()
    assert len(alerts) == 2
    assert alerts[1]["OLD_STATUS"] == "ACTION_REQUIRED"
    assert alerts[1]["NEW_STATUS"] == "NORMAL"
    assert alerts[1]["STATUS"] == "PENDING"

    print("[TEST] RECOVERY_ALERT_CREATED= True")
    print("[TEST] ALL PASS: Outbox monitor atomicity")

finally:
    # 仅清理本次测试数据
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )
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
