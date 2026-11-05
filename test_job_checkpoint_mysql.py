
import os
from datetime import datetime

from db import get_checkpoint, update_checkpoint


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    check(
        "TEST_DATABASE_SELECTED",
        os.getenv("MYSQL_DATABASE") == "opspilot_test"
    )

    monitor_name = "JOB_MONITOR_E2E6B"

    initial = get_checkpoint(monitor_name)
    old_time = initial["LAST_SCAN_TIME"]

    check(
        "INITIAL_CHECKPOINT_READ",
        old_time == datetime(2026, 10, 1)
    )

    new_time = datetime(2026, 10, 2)

    update_checkpoint(new_time, monitor_name)

    # get_checkpoint() opens a fresh database connection.
    updated = get_checkpoint(monitor_name)

    check(
        "CHECKPOINT_PERSISTED",
        updated["LAST_SCAN_TIME"] == new_time
    )

    check(
        "CHECKPOINT_STATUS_SUCCESS",
        updated["SCAN_STATUS"] == "SUCCESS"
    )

    check(
        "LAST_SUCCESS_TIME_RECORDED",
        updated["LAST_SUCCESS_TIME"] is not None
    )

    print("[TEST] ALL PASS: MySQL Checkpoint Persistence")


if __name__ == "__main__":
    main()
