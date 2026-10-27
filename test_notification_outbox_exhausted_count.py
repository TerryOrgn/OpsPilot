
from uuid import uuid4

from db import get_connection
from notification_outbox import get_exhausted_outbox_count

type_a = "T_" + uuid4().hex[:20].upper()
type_b = "T_" + uuid4().hex[:20].upper()

test_cases = [
    (type_a, "EXHAUSTED"),
    (type_a, "EXHAUSTED"),
    (type_a, "FAILED"),
    (type_b, "EXHAUSTED"),
    (type_b, "SENT"),
]

event_ids = []

try:
    # 1. 创建独立测试数据
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for notification_type, status in test_cases:
                cursor.execute(
                    """
                    INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                        (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        notification_type,
                        "DEAD_LETTER_DETECTED",
                        status
                    )
                )
                event_ids.append(cursor.lastrowid)

        conn.commit()
    finally:
        conn.close()

    # 2. 验证 Type A 统计
    count_a = get_exhausted_outbox_count(type_a)
    assert count_a == 2, f"Type A expected 2, got {count_a}"

    print("[TEST] TYPE_A_EXHAUSTED=", count_a)

    # 3. 验证 Type B 统计
    count_b = get_exhausted_outbox_count(type_b)
    assert count_b == 1, f"Type B expected 1, got {count_b}"

    print("[TEST] TYPE_B_EXHAUSTED=", count_b)

    # 4. 验证不存在的通知类型
    missing_type = "T_" + uuid4().hex[:20].upper()
    count_missing = get_exhausted_outbox_count(missing_type)

    assert count_missing == 0
    print("[TEST] MISSING_TYPE_EXHAUSTED=", count_missing)

    # 5. 验证全局统计包含本次测试的3条 EXHAUSTED
    total = get_exhausted_outbox_count()

    assert total >= 3
    print("[TEST] GLOBAL_COUNT_INCLUDES_TEST_EVENTS= True")

    print("[TEST] ALL PASS: Outbox exhausted count")

finally:
    # 只删除本次测试创建的记录
    if event_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ",".join(["%s"] * len(event_ids))

                cursor.execute(
                    f"""
                    DELETE FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE EVENT_ID IN ({placeholders})
                      AND NOTIFICATION_TYPE IN (%s, %s)
                    """,
                    (*event_ids, type_a, type_b)
                )

            conn.commit()
        finally:
            conn.close()
