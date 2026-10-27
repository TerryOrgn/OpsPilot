
from uuid import uuid4
from unittest.mock import patch

import pymysql.cursors

from db import get_connection
from notification_monitor_state import (
    transition_dead_letter_state,
    get_dead_letter_state,
)
import notification_monitor_state as monitor_state


notification_type = "T_" + uuid4().hex[:20].upper()

# 保存真实连接函数
real_get_connection = monitor_state.get_connection


class FailingCursor(pymysql.cursors.Cursor):
    def execute(self, query, args=None):
        if "INSERT INTO JOB_MONITOR_EVENT_OUTBOX" in query:
            raise RuntimeError("Simulated Outbox insert failure")
        return super().execute(query, args)


def failing_get_connection():
    conn = real_get_connection()
    conn.cursorclass = FailingCursor
    return conn


try:
    # 第一步：建立 NORMAL 基线
    assert transition_dead_letter_state(
        notification_type, "NORMAL"
    ) is None

    # 第二步：模拟 Outbox 插入失败
    with patch.object(
        monitor_state,
        "get_connection",
        side_effect=failing_get_connection
    ):
        try:
            transition_dead_letter_state(
                notification_type,
                "ACTION_REQUIRED"
            )
            raise AssertionError("Expected Outbox insert failure")
        except RuntimeError as exc:
            assert str(exc) == "Simulated Outbox insert failure"

    # 第三步：检查监控状态是否回滚
    stored_status = get_dead_letter_state(notification_type)
    assert stored_status == "NORMAL"

    # 第四步：检查 Outbox 没有残留事件
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
            count = next(iter(row.values())) if isinstance(row, dict) else row[0]
    finally:
        conn.close()

    assert count == 0

    print("[TEST] STORED_STATUS=", stored_status)
    print("[TEST] OUTBOX_COUNT=", count)
    print("[TEST] ALL PASS: Atomic rollback")

finally:
    # 清理本次测试数据
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
