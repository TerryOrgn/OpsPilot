
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    get_pending_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []

try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for status in ["PENDING", "SENT", "PENDING"]:
                cursor.execute(
                    """
                    INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                        (
                            NOTIFICATION_TYPE,
                            OLD_STATUS,
                            NEW_STATUS,
                            STATUS
                        )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        notification_type,
                        "NORMAL",
                        "ACTION_REQUIRED",
                        status,
                    )
                )
                created_ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # 只检查本次测试创建的记录
    # 避免数据库中已有的 PENDING 记录干扰断言
    all_pending = get_pending_fallback_alerts(limit=100000)
    own_pending = [
        row for row in all_pending
        if row["ALERT_ID"] in created_ids
    ]

    assert len(own_pending) == 2
    assert all(row["STATUS"] == "PENDING" for row in own_pending)
    print("[TEST] PENDING_FILTER= True")

    assert [row["ALERT_ID"] for row in own_pending] == [
        created_ids[0],
        created_ids[2],
    ]
    print("[TEST] ORDER_BY_CREATED_AT_AND_ID= True")

    assert len(get_pending_fallback_alerts(limit=1)) <= 1
    print("[TEST] LIMIT= True")

    for invalid_limit in [0, -1, True, 1.5, "10"]:
        try:
            get_pending_fallback_alerts(limit=invalid_limit)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Expected ValueError: {invalid_limit!r}"
            )

    print("[TEST] INVALID_LIMIT_REJECTED= True")
    print("[TEST] ALL PASS: Fallback alert query")

finally:
    if created_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ",".join(
                    ["%s"] * len(created_ids)
                )
                cursor.execute(
                    f"""
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID IN ({placeholders})
                    """,
                    tuple(created_ids)
                )
            conn.commit()
        finally:
            conn.close()
