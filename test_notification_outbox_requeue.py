
from uuid import uuid4

from db import get_connection
from notification_outbox import requeue_due_failed_outbox_events

notification_type = "T_" + uuid4().hex[:20].upper()
event_ids = {}


def read_events():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT EVENT_ID, STATUS, RETRY_COUNT, NEXT_RETRY_AT
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE NOTIFICATION_TYPE = %s
                """,
                (notification_type,)
            )

            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description]

            return {
                row["EVENT_ID"]: row
                for row in (
                    r if isinstance(r, dict)
                    else dict(zip(columns, r))
                    for r in rows
                )
            }
    finally:
        conn.close()


try:
    # 1. 创建四种测试事件
    cases = [
        ("FIRST_DUE", 1, -60),
        ("SECOND_DUE", 2, -60),
        ("SECOND_FUTURE", 2, 600),
        ("THIRD_DUE", 3, -60),
    ]

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for name, retry_count, offset_seconds in cases:
                cursor.execute(
                    """
                    INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                        (
                            NOTIFICATION_TYPE,
                            EVENT_TYPE,
                            STATUS,
                            RETRY_COUNT,
                            NEXT_RETRY_AT
                        )
                    VALUES (
                        %s,
                        %s,
                        'FAILED',
                        %s,
                        CURRENT_TIMESTAMP(3)
                            + INTERVAL %s SECOND
                    )
                    """,
                    (
                        notification_type,
                        "DEAD_LETTER_DETECTED",
                        retry_count,
                        offset_seconds,
                    )
                )
                event_ids[name] = cursor.lastrowid

        conn.commit()
    finally:
        conn.close()

    # 2. 只处理本次测试的通知类型
    requeued_count = requeue_due_failed_outbox_events(
        notification_type=notification_type,
        max_attempts=3
    )

    assert requeued_count == 2, (
        f"Expected 2 requeued, got {requeued_count}"
    )

    # 3. 检查最终状态
    rows = read_events()

    first = rows[event_ids["FIRST_DUE"]]
    second = rows[event_ids["SECOND_DUE"]]
    future = rows[event_ids["SECOND_FUTURE"]]
    third = rows[event_ids["THIRD_DUE"]]

    assert first["STATUS"] == "PENDING"
    assert first["NEXT_RETRY_AT"] is None
    assert first["RETRY_COUNT"] == 1

    assert second["STATUS"] == "PENDING"
    assert second["NEXT_RETRY_AT"] is None
    assert second["RETRY_COUNT"] == 2

    assert future["STATUS"] == "FAILED"
    assert future["NEXT_RETRY_AT"] is not None

    assert third["STATUS"] == "FAILED"
    assert third["RETRY_COUNT"] == 3

    print("[TEST] REQUEUED_COUNT=", requeued_count)
    print("[TEST] FIRST_DUE_REQUEUED= True")
    print("[TEST] SECOND_DUE_REQUEUED= True")
    print("[TEST] FUTURE_NOT_REQUEUED= True")
    print("[TEST] MAX_ATTEMPTS_ENFORCED= True")
    print("[TEST] ALL PASS: Outbox retry requeue")

finally:
    # 只清理本次测试创建的记录
    if event_ids:
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
            conn.commit()
        finally:
            conn.close()
