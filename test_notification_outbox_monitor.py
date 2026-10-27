
from uuid import uuid4

from db import get_connection
from notification_outbox_monitor import run_outbox_monitor


notification_type = "T_" + uuid4().hex[:20].upper()
event_id = None


def assert_result(result, status, changed, alert_emitted):
    assert result["notification_type"] == notification_type
    assert result["status"] == status, result
    assert result["changed"] is changed, result
    assert result["alert_emitted"] is alert_emitted, result


try:
    # 1. 首次扫描：没有异常
    result = run_outbox_monitor(notification_type)

    assert_result(result, "NORMAL", False, False)
    assert result["exhausted_count"] == 0

    print("[TEST] INITIAL_NORMAL= True")

    # 2. 插入一条 EXHAUSTED 事件
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

    # 3. 首次发现异常
    result = run_outbox_monitor(notification_type)

    assert_result(
        result,
        "ACTION_REQUIRED",
        True,
        True
    )
    assert result["exhausted_count"] == 1

    print("[TEST] FIRST_ALERT= True")

    # 4. 重复扫描：不重复告警
    result = run_outbox_monitor(notification_type)

    assert_result(
        result,
        "ACTION_REQUIRED",
        False,
        False
    )

    print("[TEST] DUPLICATE_SUPPRESSED= True")

    # 5. 删除测试异常，模拟恢复
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

    # 6. 扫描恢复状态
    result = run_outbox_monitor(notification_type)

    assert_result(result, "NORMAL", True, True)
    assert result["exhausted_count"] == 0

    print("[TEST] RECOVERY_ALERT= True")

    # 7. 重复正常扫描
    result = run_outbox_monitor(notification_type)

    assert_result(result, "NORMAL", False, False)

    print("[TEST] DUPLICATE_RECOVERY_SUPPRESSED= True")
    print("[TEST] ALL PASS: Outbox monitor integration")

finally:
    # 清理本次测试数据
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
