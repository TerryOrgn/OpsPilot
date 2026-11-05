
import os
from datetime import datetime, timedelta

from db import get_connection
from alert_manager import save_alert, resolve_alert
import uuid


EXECUTION_ID = f"E2E6A-{uuid.uuid4().hex[:16]}"



def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def fetch_one(sql, params):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
    finally:
        connection.close()


def main():
    # Fail closed: never run against the operational database.
    check(
        "TEST_DATABASE_SELECTED",
        os.getenv("MYSQL_DATABASE") == "opspilot_test",
    )

    connection = get_connection()
    try:
        check(
            "CONNECTED_TO_TEST_DATABASE",
            connection.db.decode() == "opspilot_test"
            if isinstance(connection.db, bytes)
            else connection.db == "opspilot_test",
        )
    finally:
        connection.close()

    now = datetime.now()

    job = {
        "EXECUTION_ID": EXECUTION_ID,
        "SYSTEM_ID": "E2E_TEST",
        "JOB_NAME": "AlertLifecycleTestJob",
        "BUSINESS_DATE": now.date(),
        "START_TIME": now - timedelta(minutes=40),
        "END_TIME": None,
        "STATUS": "RUNNING",
        "ERROR_MESSAGE": None,
    }

    # The dedicated test database must start clean.
    existing = fetch_one(
        """
        SELECT COUNT(*) AS CNT
        FROM JOB_EXECUTION_LOG
        WHERE EXECUTION_ID = %s
        """,
        (EXECUTION_ID,),
    )
    check("TEST_EXECUTION_ID_UNUSED", existing["CNT"] == 0)

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG (
                    EXECUTION_ID, SYSTEM_ID, JOB_NAME,
                    BUSINESS_DATE, START_TIME, END_TIME,
                    STATUS, ERROR_MESSAGE
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job["EXECUTION_ID"],
                    job["SYSTEM_ID"],
                    job["JOB_NAME"],
                    job["BUSINESS_DATE"],
                    job["START_TIME"],
                    job["END_TIME"],
                    job["STATUS"],
                    job["ERROR_MESSAGE"],
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    # 1. First detection creates an alert.
    first = save_alert(
        job, "JOB_TIMEOUT", "WARNING", "E2E timeout test"
    )
    check("ALERT_CREATED", first["event_type"] == "CREATED")

    # 2. Repeated detection does not create another alert.
    second = save_alert(
        job, "JOB_TIMEOUT", "WARNING", "E2E timeout test"
    )
    check("ALERT_DUPLICATE", second["event_type"] == "DUPLICATE")

    alert = fetch_one(
        """
        SELECT ID, ALERT_STATUS, DETECT_COUNT
        FROM JOB_ALERT_HISTORY
        WHERE EXECUTION_ID = %s AND ALERT_TYPE = %s
        """,
        (EXECUTION_ID, "JOB_TIMEOUT"),
    )

    check("ONE_ALERT_RECORD", alert is not None)
    check("DETECT_COUNT_TWO", alert["DETECT_COUNT"] == 2)

    # 3. Resolve the alert.
    resolved = resolve_alert(
        EXECUTION_ID, "JOB_TIMEOUT", "E2E resolution"
    )
    check("ALERT_RESOLVED", resolved is True)

    resolved_row = fetch_one(
        """
        SELECT ALERT_STATUS
        FROM JOB_ALERT_HISTORY
        WHERE ID = %s
        """,
        (alert["ID"],),
    )
    check(
        "DATABASE_STATUS_RESOLVED",
        resolved_row["ALERT_STATUS"] == "RESOLVED",
    )

    # 4. Detect again and reopen the same alert.
    reopened = save_alert(
        job, "JOB_TIMEOUT", "WARNING", "E2E reopened timeout"
    )
    check("ALERT_REOPENED", reopened["event_type"] == "REOPENED")
    check("SAME_ALERT_ID", reopened["alert_id"] == alert["ID"])

    final_row = fetch_one(
        """
        SELECT ALERT_STATUS, DETECT_COUNT
        FROM JOB_ALERT_HISTORY
        WHERE ID = %s
        """,
        (alert["ID"],),
    )
    check("DATABASE_STATUS_OPEN",
          final_row["ALERT_STATUS"] == "OPEN")
    check("DETECT_COUNT_THREE",
          final_row["DETECT_COUNT"] == 3)

    audit = fetch_one(
        """
        SELECT
            COUNT(*) AS CNT,
            SUM(CHANGE_TYPE = 'CREATE') AS CREATED,
            SUM(CHANGE_TYPE = 'AUTO_RESOLVE') AS RESOLVED,
            SUM(CHANGE_TYPE = 'REOPEN') AS REOPENED
        FROM JOB_ALERT_STATUS_HISTORY
        WHERE ALERT_ID = %s
        """,
        (alert["ID"],),
    )

    check("THREE_AUDIT_EVENTS", audit["CNT"] == 3)
    check(
        "AUDIT_EVENT_TYPES_CORRECT",
        audit["CREATED"] == 1
        and audit["RESOLVED"] == 1
        and audit["REOPENED"] == 1,
    )

    notifications = fetch_one(
        """
        SELECT COUNT(*) AS CNT
        FROM JOB_NOTIFICATION_HISTORY
        WHERE ALERT_ID = %s
        """,
        (alert["ID"],),
    )
    check("TWO_NOTIFICATION_TASKS", notifications["CNT"] == 2)

    print("[TEST] ALL PASS: MySQL Alert Lifecycle")


if __name__ == "__main__":
    main()
