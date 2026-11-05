
import os
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection
from alert_manager import save_alert
from notification_worker import claim_notification


def create_test_notification():
    execution_id = "E2E10B_" + uuid.uuid4().hex[:16]

    job = {
        "EXECUTION_ID": execution_id,
        "SYSTEM_ID": "E2E_TEST",
        "JOB_NAME": "E2E10B_TestJob",
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
                )
            )
        conn.commit()
    finally:
        conn.close()

    result = save_alert(
        job,
        "JOB_FAILED",
        "CRITICAL",
        "E2E10B test failure",
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
                (result["alert_id"],)
            )
            row = cursor.fetchone()
            assert row is not None
            return execution_id, result["alert_id"], row["ID"]
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
                (execution_id,)
            )
            cursor.execute(
                """
                DELETE FROM JOB_ALERT_STATUS_HISTORY
                WHERE ALERT_ID IN (
                    SELECT ID FROM JOB_ALERT_HISTORY
                    WHERE EXECUTION_ID = %s
                )
                """,
                (execution_id,)
            )
            cursor.execute(
                """
                DELETE FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                """,
                (execution_id,)
            )
            cursor.execute(
                """
                DELETE FROM JOB_EXECUTION_LOG
                WHERE EXECUTION_ID = %s
                """,
                (execution_id,)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_single_claim():
    execution_id = None
    try:
        execution_id, alert_id, notification_id = (
            create_test_notification()
        )

        first = claim_notification(notification_id)
        assert first is not None
        assert first["ID"] == notification_id
        assert first["CLAIM_TOKEN"]

        print("[TEST] FIRST_CLAIM=PASS")

        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT NOTIFICATION_STATUS,
                           CLAIM_TOKEN,
                           PROCESSING_STARTED_AT
                    FROM JOB_NOTIFICATION_HISTORY
                    WHERE ID = %s
                    """,
                    (notification_id,)
                )
                row = cursor.fetchone()
        finally:
            conn.close()

        assert row["NOTIFICATION_STATUS"] == "PROCESSING"
        assert row["CLAIM_TOKEN"] == first["CLAIM_TOKEN"]
        assert row["PROCESSING_STARTED_AT"] is not None

        print("[TEST] PROCESSING_STATE=PASS")

        second = claim_notification(notification_id)
        assert second is None

        print("[TEST] DUPLICATE_CLAIM_PREVENTED=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


def test_concurrent_claim():
    execution_id = None
    try:
        execution_id, alert_id, notification_id = (
            create_test_notification()
        )

        barrier = threading.Barrier(2)

        def worker():
            barrier.wait(timeout=10)
            return claim_notification(notification_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            results = [f.result(timeout=20) for f in futures]

        winners = [r for r in results if r is not None]
        losers = [r for r in results if r is None]

        assert len(winners) == 1, results
        assert len(losers) == 1, results

        print("[TEST] CONCURRENT_CLAIM=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


if __name__ == "__main__":
    test_single_claim()
    test_concurrent_claim()
    print("[TEST] ALL PASS: JOB-E2E-10B")
