
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from db import get_connection
from notification_outbox_monitor_state import (
    transition_outbox_monitor_state,
)

notification_type = "T_" + uuid4().hex[:20].upper()


def worker():
    return transition_outbox_monitor_state(
        notification_type,
        "ACTION_REQUIRED"
    )


try:
    # 1. 预先建立 NORMAL 基线
    baseline = transition_outbox_monitor_state(
        notification_type,
        "NORMAL"
    )

    assert baseline["changed"] is False

    # 2. 两个线程同时尝试转换状态
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker)
            for _ in range(2)
        ]
        results = [future.result() for future in futures]

    # 3. 只能有一个线程成功完成状态转换
    changed_count = sum(
        1 for result in results if result["changed"]
    )

    unchanged_count = sum(
        1 for result in results if not result["changed"]
    )

    assert changed_count == 1, results
    assert unchanged_count == 1, results

    print("[TEST] CHANGED_COUNT=", changed_count)
    print("[TEST] UNCHANGED_COUNT=", unchanged_count)

    # 4. 数据库最终状态必须正确
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
            status = (
                row["EXHAUSTED_STATUS"]
                if isinstance(row, dict)
                else row[0]
            )

            assert status == "ACTION_REQUIRED"

    finally:
        conn.close()

    print("[TEST] FINAL_STATUS= ACTION_REQUIRED")
    print("[TEST] ALL PASS: Outbox monitor concurrency")

finally:
    # 只清理本次测试数据
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
