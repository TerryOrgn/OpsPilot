
import time
from uuid import uuid4

from db import get_connection
from notification_outbox_monitor_scheduler import (
    start_outbox_monitor_scheduler,
)

notification_type = "T_" + uuid4().hex[:20].upper()
scheduler = None
event_id = None


def read_monitor_status():
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


def wait_for_status(expected_status, timeout=8):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if read_monitor_status() == expected_status:
            return True

        time.sleep(0.2)

    return False


try:
    # 1. 启动真实监控调度器
    scheduler = start_outbox_monitor_scheduler(
        notification_type=notification_type,
        interval_seconds=1
    )

    assert scheduler.running
    print("[TEST] SCHEDULER_STARTED= True")

    # 2. 等待初始 NORMAL 状态建立
    assert wait_for_status("NORMAL")
    print("[TEST] INITIAL_NORMAL= True")

    # 3. 插入一条最终失败事件
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                    (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                VALUES (%s, %s, 'EXHAUSTED')
                """,
                (
                    notification_type,
                    "DEAD_LETTER_DETECTED"
                )
            )
            event_id = cursor.lastrowid

        conn.commit()
    finally:
        conn.close()

    # 4. 等待调度器自动发现异常
    assert wait_for_status("ACTION_REQUIRED")
    print("[TEST] AUTO_DETECT_EXHAUSTED= True")

    # 5. 模拟异常清零
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
        event_id = None
    finally:
        conn.close()

    # 6. 等待调度器自动发现恢复
    assert wait_for_status("NORMAL")
    print("[TEST] AUTO_DETECT_RECOVERY= True")

    print("[TEST] ALL PASS: Outbox scheduler integration")

finally:
    # 先停止调度器，再清理测试数据
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=True)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            if event_id is not None:
                cursor.execute(
                    """
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE EVENT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (event_id, notification_type)
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
