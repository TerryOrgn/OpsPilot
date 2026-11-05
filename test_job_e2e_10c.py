
import os
import uuid

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection
from alert_manager import save_alert
from notification_worker import (
    claim_notification,
    complete_notification,
)


def create_test_notification():
    execution_id = "E2E10C_" + uuid.uuid4().hex[:16]

    job = {
        "EXECUTION_ID": execution_id,
        "SYSTEM_ID": "E2E_TEST",
        "JOB_NAME": "E2E10C_TestJob",
    }

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            assert cursor.fetchone()["db"] == "opspilot_test"

            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG (
                    EXECUTION_ID, SYSTEM_ID, JOB_NAME,
                    BUSINESS_DATE, START_TIME, END_TIME, STATUS
                )
                VALUES (
                    %s, %s, %s,
                    CURRENT_DATE(), NOW(3), NOW(3), 'FAILED'
                )
                """,
                (
                    execution_id,
                    job["SYSTEM_ID"],
                    job["JOB_NAME"],
                ),
            )
        conn.commit()
    finally:
        conn.close()

    result = save_alert(
        job,
        "JOB_FAILED",
        "CRITICAL",
        "E2E10C test failure",
    )

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ID
                FROM JOB_NOTIFICATION_HISTORY
                WHERE ALERT_ID = %s
                  AND NOTIFICATION_STATUS = 'PENDING'
                """,
                (result["alert_id"],),
            )
            notification = cursor.fetchone()
            assert notification is not None
            return execution_id, notification["ID"]
    finally:
        conn.close()


def get_notification(notification_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT NOTIFICATION_STATUS, RETRY_COUNT,
                       SENT_AT, LAST_ERROR_MESSAGE,
                       CLAIM_TOKEN, PROCESSING_STARTED_AT
                FROM JOB_NOTIFICATION_HISTORY
                WHERE ID = %s
                """,
                (notification_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


def cleanup(execution_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM JOB_NOTIFICATION_HISTORY
                WHERE ALERT_ID IN (
                    SELECT ID FROM JOB_ALERT_HISTORY
                    WHERE EXECUTION_ID = %s
                )
                """,
                (execution_id,),
            )
            cursor.execute(
                """
                DELETE FROM JOB_ALERT_STATUS_HISTORY
                WHERE ALERT_ID IN (
                    SELECT ID FROM JOB_ALERT_HISTORY
                    WHERE EXECUTION_ID = %s
                )
                """,
                (execution_id,),
            )
            cursor.execute(
                """
                DELETE FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                """,
                (execution_id,),
            )
            cursor.execute(
                """
                DELETE FROM JOB_EXECUTION_LOG
                WHERE EXECUTION_ID = %s
                """,
                (execution_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_success():
    execution_id = None
    try:
        execution_id, notification_id = create_test_notification()
        task = claim_notification(notification_id)
        assert task is not None

        token = task["CLAIM_TOKEN"]

        assert complete_notification(
            notification_id, token, success=True
        ) is True

        row = get_notification(notification_id)

        assert row["NOTIFICATION_STATUS"] == "SENT"
        assert row["SENT_AT"] is not None
        assert row["RETRY_COUNT"] == 0
        assert row["LAST_ERROR_MESSAGE"] is None
        assert row["CLAIM_TOKEN"] is None
        assert row["PROCESSING_STARTED_AT"] is None

        print("[TEST] SUCCESS_CONFIRMATION=PASS")

        assert complete_notification(
            notification_id, token, success=True
        ) is False

        print("[TEST] DUPLICATE_CONFIRMATION=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


def test_failure():
    execution_id = None
    try:
        execution_id, notification_id = create_test_notification()
        task = claim_notification(notification_id)
        assert task is not None

        token = task["CLAIM_TOKEN"]

        assert complete_notification(
            notification_id,
            "invalid-token",
            success=True,
        ) is False

        row = get_notification(notification_id)
        assert row["NOTIFICATION_STATUS"] == "PROCESSING"
        assert row["CLAIM_TOKEN"] == token

        print("[TEST] INVALID_TOKEN_REJECTED=PASS")

        assert complete_notification(
            notification_id,
            token,
            success=False,
            error_message="Simulated delivery failure",
        ) is True

        row = get_notification(notification_id)

        assert row["NOTIFICATION_STATUS"] == "FAILED"
        assert row["RETRY_COUNT"] == 1
        assert row["LAST_ERROR_MESSAGE"] == (
            "Simulated delivery failure"
        )
        assert row["SENT_AT"] is None
        assert row["CLAIM_TOKEN"] is None
        assert row["PROCESSING_STARTED_AT"] is None

        print("[TEST] FAILURE_CONFIRMATION=PASS")

        assert complete_notification(
            notification_id,
            token,
            success=False,
        ) is False

        assert get_notification(notification_id)["RETRY_COUNT"] == 1

        print("[TEST] FAILURE_IDEMPOTENCY=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


if __name__ == "__main__":
    test_success()
    test_failure()
    print("[TEST] ALL PASS: JOB-E2E-10C")
