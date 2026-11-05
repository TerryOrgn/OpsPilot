
import os

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from notification_worker import (
    claim_notification,
    complete_notification,
)
from test_job_e2e_10c import (
    create_test_notification,
    get_notification,
    cleanup,
)


def test_exhausted():
    execution_id = None

    try:
        execution_id, notification_id = create_test_notification()

        tokens = []

        for attempt in range(1, 4):
            task = claim_notification(notification_id)
            assert task is not None, f"Attempt {attempt} claim failed"

            token = task["CLAIM_TOKEN"]
            assert token not in tokens
            tokens.append(token)

            assert complete_notification(
                notification_id,
                token,
                success=False,
                error_message=f"Simulated failure {attempt}",
            ) is True

            row = get_notification(notification_id)

            assert row["RETRY_COUNT"] == attempt

            expected_status = (
                "EXHAUSTED" if attempt == 3 else "FAILED"
            )

            assert row["NOTIFICATION_STATUS"] == expected_status
            assert row["CLAIM_TOKEN"] is None

            print(f"[TEST] FAILURE_ATTEMPT_{attempt}=PASS")

        assert claim_notification(notification_id) is None

        print("[TEST] EXHAUSTED_NOT_RECLAIMED=PASS")
        print("[TEST] UNIQUE_CLAIM_TOKENS=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


def test_success_after_retry():
    execution_id = None

    try:
        execution_id, notification_id = create_test_notification()

        first = claim_notification(notification_id)
        assert first is not None

        assert complete_notification(
            notification_id,
            first["CLAIM_TOKEN"],
            success=False,
            error_message="Transient failure",
        ) is True

        row = get_notification(notification_id)
        assert row["NOTIFICATION_STATUS"] == "FAILED"
        assert row["RETRY_COUNT"] == 1

        second = claim_notification(notification_id)
        assert second is not None
        assert second["CLAIM_TOKEN"] != first["CLAIM_TOKEN"]

        assert complete_notification(
            notification_id,
            second["CLAIM_TOKEN"],
            success=True,
        ) is True

        row = get_notification(notification_id)

        assert row["NOTIFICATION_STATUS"] == "SENT"
        assert row["RETRY_COUNT"] == 1
        assert row["SENT_AT"] is not None

        assert claim_notification(notification_id) is None

        print("[TEST] SUCCESS_AFTER_RETRY=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


if __name__ == "__main__":
    test_exhausted()
    test_success_after_retry()
    print("[TEST] ALL PASS: JOB-E2E-10E")
