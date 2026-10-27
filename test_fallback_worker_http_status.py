
from urllib.error import HTTPError

from db import get_connection
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)


def create_alert():
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

            alert_id = cursor.lastrowid

        conn.commit()
        return alert_id

    finally:
        conn.close()


def get_alert(alert_id):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT STATUS, RETRY_COUNT,
                       CLAIM_TOKEN, NEXT_RETRY_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))

            return cursor.fetchone()

    finally:
        conn.close()


def delete_alert(alert_id):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE ALERT_ID = %s
            """, (alert_id,))

        conn.commit()

    finally:
        conn.close()


def mock_http_200(alert):
    return True


def mock_http_409(alert):
    raise HTTPError(
        url="http://127.0.0.1/webhook",
        code=409,
        msg="Conflict",
        hdrs={},
        fp=None,
    )


def mock_http_500(alert):
    raise HTTPError(
        url="http://127.0.0.1/webhook",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=None,
    )


def run_case(name, sender, expected_status, counter):
    alert_id = create_alert()

    try:
        result = run_fallback_worker(
            send_alert=sender,
            limit=1,
        )

        row = get_alert(alert_id)

        assert result["claimed"] == 1, result
        assert result[counter] == 1, result
        assert result["confirmation_errors"] == 0, result

        assert row is not None
        assert row["STATUS"] == expected_status, row
        assert row["RETRY_COUNT"] == 1, row
        assert row["CLAIM_TOKEN"] is None, row

        if expected_status == "FAILED":
            assert row["NEXT_RETRY_AT"] is not None
        else:
            assert row["NEXT_RETRY_AT"] is None

        print(f"[TEST] {name}= True")

    finally:
        delete_alert(alert_id)


# 运行前要求：测试数据库没有其他 PENDING 告警
run_case(
    "HTTP_200_SENT",
    mock_http_200,
    "SENT",
    "sent",
)

run_case(
    "HTTP_409_EXHAUSTED",
    mock_http_409,
    "EXHAUSTED",
    "conflicted",
)

run_case(
    "HTTP_500_FAILED",
    mock_http_500,
    "FAILED",
    "failed",
)

print("[TEST] ALL PASS: Worker HTTP status handling")
