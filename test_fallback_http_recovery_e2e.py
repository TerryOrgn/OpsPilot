
import os
import threading
from unittest.mock import patch

from db import get_connection
import notification_outbox_fallback_worker as worker
from notification_outbox_fallback_dispatcher import (
    recover_stale_fallback_alerts,
)
from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)
from webhook_idempotency_http import create_webhook_server


alert_id = None
server = None
server_thread = None
old_webhook_url = os.environ.get(
    "OPSPILOT_FALLBACK_WEBHOOK_URL"
)


def query_one(sql, params):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        conn.close()


def get_status(alert_id):
    row = query_one("""
        SELECT STATUS
        FROM JOB_OUTBOX_FALLBACK_ALERT
        WHERE ALERT_ID = %s
    """, (alert_id,))
    return row["STATUS"]


def get_business_count(key):
    row = query_one("""
        SELECT COUNT(*) AS TOTAL
        FROM WEBHOOK_BUSINESS_TEST
        WHERE IDEMPOTENCY_KEY = %s
    """, (key,))
    return row["TOTAL"]


def insert_alert():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE, OLD_STATUS,
                     NEW_STATUS, STATUS)
                VALUES (%s, %s, %s, 'PENDING')
            """, (
                "OUTBOX_EXHAUSTED",
                "NORMAL",
                "ACTION_REQUIRED",
            ))
            new_id = cursor.lastrowid
        conn.commit()
        return new_id
    finally:
        conn.close()


def make_claim_stale(alert_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET CLAIMED_AT =
                    CURRENT_TIMESTAMP(3) - INTERVAL 10 MINUTE
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
            """, (alert_id,))
            assert cursor.rowcount == 1
        conn.commit()
    finally:
        conn.close()


def cleanup(alert_id):
    key = str(alert_id)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM WEBHOOK_BUSINESS_TEST
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
            cursor.execute("""
                DELETE FROM WEBHOOK_IDEMPOTENCY
                WHERE IDEMPOTENCY_KEY = %s
            """, (key,))
            cursor.execute("""
                DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))
        conn.commit()
    finally:
        conn.close()


try:
    # 1. 启动真实 HTTP Server
    server = create_webhook_server(
        host="127.0.0.1",
        port=0,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    server_thread.start()

    port = server.server_address[1]
    os.environ["OPSPILOT_FALLBACK_WEBHOOK_URL"] = (
        f"http://127.0.0.1:{port}/webhook"
    )

    # 2. 创建告警
    alert_id = insert_alert()
    key = str(alert_id)

    # 3. 第一次投递：HTTP 成功，模拟确认失败
    real_confirm_sent = worker.confirm_fallback_alert_sent

    def simulate_confirmation_failure(
        claimed_alert_id,
        claim_token,
    ):
        assert claimed_alert_id == alert_id
        raise RuntimeError(
            "Simulated sender DB confirmation failure"
        )

    with patch.object(
        worker,
        "confirm_fallback_alert_sent",
        side_effect=simulate_confirmation_failure,
    ):
        first = worker.run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=1,
        )

    assert first["claimed"] == 1, first
    assert first["confirmation_errors"] == 1, first
    assert get_status(alert_id) == "PROCESSING"
    assert get_business_count(key) == 1

    print("[TEST] FIRST_HTTP_DELIVERY= True")
    print("[TEST] SENDER_CONFIRMATION_FAILED= True")

    # 4. 模拟超时恢复
    make_claim_stale(alert_id)

    recover_stale_fallback_alerts(
        timeout_seconds=300,
        max_attempts=3,
    )

    assert get_status(alert_id) == "PENDING"
    print("[TEST] STALE_RECOVERY= True")

    # 5. 第二次真实 HTTP 投递
    second = worker.run_fallback_worker(
        send_alert=send_fallback_webhook,
        limit=1,
    )

    assert second["claimed"] == 1, second
    assert second["sent"] == 1, second
    assert second["confirmation_errors"] == 0, second

    assert get_status(alert_id) == "SENT"
    assert get_business_count(key) == 1

    print("[TEST] SECOND_HTTP_DELIVERY= True")
    print("[TEST] FINAL_STATUS_SENT= True")
    print("[TEST] BUSINESS_EXECUTED_ONCE= True")
    print("[TEST] ALL PASS: Fallback HTTP recovery E2E")

finally:
    if alert_id is not None:
        cleanup(alert_id)

    if server is not None:
        server.shutdown()
        server.server_close()

    if server_thread is not None:
        server_thread.join(timeout=5)

    if old_webhook_url is None:
        os.environ.pop(
            "OPSPILOT_FALLBACK_WEBHOOK_URL",
            None,
        )
    else:
        os.environ[
            "OPSPILOT_FALLBACK_WEBHOOK_URL"
        ] = old_webhook_url
