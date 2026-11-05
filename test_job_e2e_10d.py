
import os
from unittest.mock import patch

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from notification_worker import send_console_notification
from test_job_e2e_10c import (
    create_test_notification,
    get_notification,
    cleanup,
)


def test_success():
    execution_id = None

    try:
        execution_id, notification_id = create_test_notification()

        result = send_console_notification(notification_id)
        assert result is True

        row = get_notification(notification_id)

        assert row["NOTIFICATION_STATUS"] == "SENT"
        assert row["SENT_AT"] is not None
        assert row["RETRY_COUNT"] == 0
        assert row["CLAIM_TOKEN"] is None

        print("[TEST] CONSOLE_SEND_SUCCESS=PASS")

        # 已发送任务不能再次领取
        second = send_console_notification(notification_id)
        assert second is False

        print("[TEST] DUPLICATE_SEND_PREVENTED=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


def test_failure():
    execution_id = None

    try:
        execution_id, notification_id = create_test_notification()

        original_print = print

        def fake_print(*args, **kwargs):
            if args and str(args[0]).startswith("[NOTIFICATION]"):
                raise RuntimeError("Simulated console failure")
            return original_print(*args, **kwargs)

        try:
            with patch("builtins.print", side_effect=fake_print):
                send_console_notification(notification_id)
        except RuntimeError as exc:
            assert str(exc) == "Simulated console failure"
        else:
            raise AssertionError("Expected console failure")

        row = get_notification(notification_id)

        assert row["NOTIFICATION_STATUS"] == "FAILED"
        assert row["RETRY_COUNT"] == 1
        assert row["LAST_ERROR_MESSAGE"] == (
            "Simulated console failure"
        )
        assert row["CLAIM_TOKEN"] is None

        print("[TEST] CONSOLE_SEND_FAILURE=PASS")

    finally:
        if execution_id:
            cleanup(execution_id)


if __name__ == "__main__":
    test_success()
    test_failure()
    print("[TEST] ALL PASS: JOB-E2E-10D")
