
from uuid import uuid4

from db import get_connection
from notification_outbox_fallback_dispatcher import (
    recover_stale_fallback_alerts,
)
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)

notification_type = "T_" + uuid4().hex[:20].upper()
alert_id = None
delivered = []


def read_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, CLAIMED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
                """,
                (alert_id,)
            )
            row = cursor.fetchone()
            columns = [c[0] for c in cursor.description]
            return (
                row if isinstance(row, dict)
                else dict(zip(columns, row))
            )
    finally:
        conn.close()


def fake_send(alert):
    delivered.append(alert["ALERT_ID"])


try:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM JOB_OUTBOX_FALLBACK_ALERT"
            )
            row = cursor.fetchone()
            count = (
                next(iter(row.values()))
                if isinstance(row, dict)
                else row[0]
            )
            assert count == 0, "Use an empty isolated test database"

            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (
                        NOTIFICATION_TYPE,
                        OLD_STATUS,
                        NEW_STATUS,
                        STATUS,
                        CLAIM_TOKEN,
                        CLAIMED_AT,
                        RETRY_COUNT
                    )
                VALUES (
                    %s,
                    'NORMAL',
                    'ACTION_REQUIRED',
                    'PROCESSING',
                    %s,
                    DATE_SUB(
                        CURRENT_TIMESTAMP(3),
                        INTERVAL 600 SECOND
                    ),
                    1
                )
                """,
                (notification_type, str(uuid4()))
            )
            alert_id = cursor.lastrowid

        conn.commit()
    finally:
        conn.close()

    # 第一步：恢复超时领取
    recovered = recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )

    assert recovered == 1

    stored = read_alert()
    assert stored["STATUS"] == "PENDING"
    assert stored["RETRY_COUNT"] == 1
    assert stored["CLAIM_TOKEN"] is None
    assert stored["CLAIMED_AT"] is None

    print("[TEST] STALE_RECOVERED= True")
    print("[TEST] RETRY_COUNT_PRESERVED= True")

    # 第二步：Worker 重新领取并模拟发送成功
    result = run_fallback_worker(
        send_alert=fake_send,
        limit=1,
    )

    assert result == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "confirmation_errors": 0,
    }

    assert delivered == [alert_id]

    final = read_alert()
    assert final["STATUS"] == "SENT"
    assert final["RETRY_COUNT"] == 2
    assert final["CLAIM_TOKEN"] is None
    assert final["CLAIMED_AT"] is None

    print("[TEST] RECOVERED_ALERT_SENT= True")
    print("[TEST] SECOND_CLAIM_COUNT= True")
    print("[TEST] ALL PASS: Fallback recovery E2E")

finally:
    if alert_id is not None:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                    WHERE ALERT_ID = %s
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (alert_id, notification_type)
                )
            conn.commit()
        finally:
            conn.close()
