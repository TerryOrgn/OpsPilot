
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
)

notification_type = "T_" + uuid4().hex[:20].upper()
created_ids = []
barrier = Barrier(2)


def worker():
    barrier.wait(timeout=10)
    return claim_pending_fallback_alerts(limit=5)


try:
    # 确保测试不会领取已有业务记录
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS TOTAL
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE STATUS = 'PENDING'
                """
            )
            row = cursor.fetchone()
            pending_count = (
                row["TOTAL"]
                if isinstance(row, dict)
                else row[0]
            )

            assert pending_count == 0, (
                "Existing PENDING alerts found. "
                "Stop test to avoid modifying them."
            )

            for _ in range(10):
                cursor.execute(
                    """
                    INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                        (
                            NOTIFICATION_TYPE,
                            OLD_STATUS,
                            NEW_STATUS
                        )
                    VALUES (%s, 'NORMAL', 'ACTION_REQUIRED')
                    """,
                    (notification_type,)
                )
                created_ids.append(cursor.lastrowid)

        conn.commit()
    finally:
        conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker)
            for _ in range(2)
        ]
        results = [future.result(timeout=20) for future in futures]

    all_claimed = [
        alert
        for result in results
        for alert in result
    ]

    claimed_ids = [
        alert["ALERT_ID"]
        for alert in all_claimed
    ]

    assert len(claimed_ids) == len(set(claimed_ids))
    print("[TEST] NO_DUPLICATE_CLAIM= True")

    print("[DEBUG] WORKER_1_COUNT=", len(results[0]))
    print("[DEBUG] WORKER_2_COUNT=", len(results[1]))
    print("[DEBUG] TOTAL_CLAIMED=", len(claimed_ids))
    print("[DEBUG] CLAIMED_IDS=", sorted(claimed_ids))
    print("[DEBUG] EXPECTED_IDS=", sorted(created_ids))

    # 第一轮必须保证没有重复领取
    assert len(claimed_ids) == len(set(claimed_ids))

    # 第二轮领取剩余 PENDING 告警
    remaining = claim_pending_fallback_alerts(limit=10)

    remaining_ids = [
        alert["ALERT_ID"]
        for alert in remaining
    ]

    print("[DEBUG] SECOND_ROUND_COUNT=", len(remaining_ids))
    print("[DEBUG] SECOND_ROUND_IDS=", sorted(remaining_ids))

    # 合并两轮结果
    all_claimed.extend(remaining)
    claimed_ids.extend(remaining_ids)

    assert len(claimed_ids) == len(set(claimed_ids))
    assert set(claimed_ids) == set(created_ids)

    print("[TEST] ALL_TEN_ALERTS_CLAIMED= True")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(created_ids))
            cursor.execute(
                f"""
                SELECT ALERT_ID, STATUS, CLAIM_TOKEN
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID IN ({placeholders})
                """,
                tuple(created_ids)
            )
            rows = cursor.fetchall()

            for row in rows:
                status = (
                    row["STATUS"]
                    if isinstance(row, dict)
                    else row[1]
                )
                token = (
                    row["CLAIM_TOKEN"]
                    if isinstance(row, dict)
                    else row[2]
                )
                assert status == "PROCESSING"
                assert token is not None
    finally:
        conn.close()

    print("[TEST] CLAIM_STATE_PERSISTED= True")
    print("[TEST] ALL PASS: Fallback concurrent claim")

finally:
    if created_ids:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                placeholders = ",".join(["%s"] * len(created_ids))
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
