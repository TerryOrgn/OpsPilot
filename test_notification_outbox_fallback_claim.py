
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []


def read_alert(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, CLAIM_TOKEN,
                       CLAIMED_AT, RETRY_COUNT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            if isinstance(row, dict):
                return row
            columns = [c[0] for c in cursor.description]
            return dict(zip(columns, row))
    finally:
        conn.close()


try:
    # 创建两条隔离测试数据
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for _ in range(2):
                cursor.execute(
                    """
                    INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                        (NOTIFICATION_TYPE,
                         OLD_STATUS, NEW_STATUS)
                    VALUES (%s, 'NORMAL', 'ACTION_REQUIRED')
                    """,
                    (notification_type,)
                )
                created_ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    # 领取待处理告警
    # 注意：如果数据库已有其他 PENDING 记录，
    # 此函数也可能领取它们。
    claimed = claim_pending_fallback_alerts(limit=100000)

    own_claimed = [
        alert for alert in claimed
        if alert["ALERT_ID"] in created_ids
    ]

    assert len(own_claimed) == 2
    print("[TEST] CLAIM_TWO_ALERTS= True")

    for alert in own_claimed:
        stored = read_alert(alert["ALERT_ID"])

        assert stored["STATUS"] == "PROCESSING"
        assert stored["CLAIM_TOKEN"] == alert["CLAIM_TOKEN"]
        assert stored["CLAIMED_AT"] is not None
        assert stored["RETRY_COUNT"] == 1

    print("[TEST] CLAIM_STATE_PERSISTED= True")

    # 已领取的记录不能再次作为 PENDING 被领取
    second_claim = claim_pending_fallback_alerts(limit=100000)
    second_ids = {
        alert["ALERT_ID"] for alert in second_claim
    }

    assert not second_ids.intersection(created_ids)
    print("[TEST] DUPLICATE_CLAIM_PREVENTED= True")

    print("[TEST] ALL PASS: Fallback alert claim")

finally:
    # 仅删除本次测试创建的数据
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
