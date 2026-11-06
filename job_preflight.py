"""Read-only readiness checks for the JOB scheduler."""
import os

from db import get_connection
from job_runtime import RuntimeConfig

# The columns that distinguish the notification worker schema from older releases.
REQUIRED_COLUMNS = {
    "JOB_EXECUTION_LOG": "ID, EXECUTION_ID, STATUS, UPDATED_AT",
    "JOB_MONITOR_CHECKPOINT": "MONITOR_NAME, LAST_SCAN_TIME, LAST_SUCCESS_TIME, SCAN_STATUS, LAST_ERROR_MESSAGE",
    "JOB_ALERT_HISTORY": "ID, EXECUTION_ID, ALERT_TYPE, ALERT_STATUS",
    "JOB_ALERT_STATUS_HISTORY": "ID, ALERT_ID, CHANGE_TYPE",
    "JOB_NOTIFICATION_HISTORY": (
        "ID, EVENT_ID, ALERT_ID, NOTIFICATION_TYPE, NOTIFICATION_STATUS, "
        "CREATED_AT, UPDATED_AT, PROCESSING_STARTED_AT, CLAIM_TOKEN, "
        "RETRY_COUNT, LAST_ERROR_MESSAGE, SENT_AT"
    ),
}


def check_readiness(config=None):
    target = os.getenv("MYSQL_DATABASE")
    expected = os.getenv("OPSPILOT_EXPECTED_DATABASE")
    if not target or target != expected:
        raise RuntimeError("Set MYSQL_DATABASE and OPSPILOT_EXPECTED_DATABASE to the same explicit target")
    if config is None:
        RuntimeConfig.from_env()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            for table, columns in REQUIRED_COLUMNS.items():
                # Identifiers come exclusively from the constants above.
                cursor.execute(f"SELECT {columns} FROM {table} LIMIT 0")
            cursor.execute(
                "SELECT LAST_SCAN_TIME FROM JOB_MONITOR_CHECKPOINT WHERE MONITOR_NAME = %s",
                ("JOB_MONITOR",),
            )
            checkpoint = cursor.fetchone()
            if checkpoint is None or checkpoint["LAST_SCAN_TIME"] is None:
                raise RuntimeError("JOB_MONITOR checkpoint missing or uninitialized")
        return target
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        database = check_readiness()
    except Exception as exc:
        # Driver errors can contain connection details. Report only their category.
        detail = str(exc) if type(exc) is RuntimeError else type(exc).__name__
        raise SystemExit(f"JOB preflight failed: {detail}") from None
    print(f"JOB preflight passed for {database} (read-only)")
