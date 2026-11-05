
import os
from datetime import datetime

from db import get_connection, get_checkpoint, update_checkpoint


MONITOR_NAME = "JOB_MONITOR_E2E6C"


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    check(
        "TEST_DATABASE_SELECTED",
        os.getenv("MYSQL_DATABASE") == "opspilot_test",
    )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS DB_NAME")
            database_name = cursor.fetchone()["DB_NAME"]

        check(
            "CONNECTED_TO_TEST_DATABASE",
            database_name == "opspilot_test",
        )
    finally:
        connection.close()

    initial_time = datetime(2026, 10, 1, 10, 0)
    newer_time = datetime(2026, 10, 1, 10, 5)
    older_time = datetime(2026, 10, 1, 10, 2)

    # Prepare an isolated checkpoint row.
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_CHECKPOINT (
                    MONITOR_NAME,
                    LAST_SCAN_TIME,
                    SCAN_STATUS
                )
                VALUES (%s, %s, 'IDLE')
                ON DUPLICATE KEY UPDATE
                    LAST_SCAN_TIME = VALUES(LAST_SCAN_TIME),
                    SCAN_STATUS = 'IDLE'
                """,
                (MONITOR_NAME, initial_time),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    check(
        "INITIAL_CHECKPOINT",
        get_checkpoint(MONITOR_NAME)["LAST_SCAN_TIME"] == initial_time,
    )

    # Process B completes the newer scan first.
    update_checkpoint(newer_time, MONITOR_NAME)

    check(
        "NEWER_SCAN_ADVANCED",
        get_checkpoint(MONITOR_NAME)["LAST_SCAN_TIME"] == newer_time,
    )

    # Process A finishes later with an older scan upper bound.
    update_checkpoint(older_time, MONITOR_NAME)

    final_time = get_checkpoint(MONITOR_NAME)["LAST_SCAN_TIME"]

    print("[DEBUG] EXPECTED_CHECKPOINT:", newer_time)
    print("[DEBUG] ACTUAL_CHECKPOINT:", final_time)

    check(
        "CHECKPOINT_NEVER_REGRESSES",
        final_time == newer_time,
    )

    print("[TEST] ALL PASS: Checkpoint Regression Protection")


if __name__ == "__main__":
    main()
