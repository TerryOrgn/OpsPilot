
from unittest.mock import patch

from notification_scheduler import run_notification_cycle


def test_dispatcher_failure():
    # 模拟一个通知发送失败
    fake_dispatch_result = {
        "claimed": 1,
        "sent": 0,
        "failed": 1,
        "errors": 0
    }

    with (
        patch(
            "notification_scheduler.recover_stale_notifications",
            return_value=0
        ),
        patch(
            "notification_scheduler.mark_exhausted_notifications",
            return_value=0
        ),
        patch(
            "notification_scheduler.mark_stale_processing_exhausted",
            return_value=0
        ),
        patch(
            "notification_scheduler.dispatch_claimed_notifications",
            return_value=fake_dispatch_result
        )
    ):
        result = run_notification_cycle(
            notification_type="CONSOLE_TEST_CYCLE",
            limit=1
        )

    assert result["cycle_status"] == "FAILED"
    print("[TEST] PASS: Dispatcher failure -> FAILED")


def test_dispatcher_error():
    # 模拟一个通知处理异常
    fake_dispatch_result = {
        "claimed": 1,
        "sent": 0,
        "failed": 0,
        "errors": 1
    }

    with (
        patch(
            "notification_scheduler.recover_stale_notifications",
            return_value=0
        ),
        patch(
            "notification_scheduler.mark_exhausted_notifications",
            return_value=0
        ),
        patch(
            "notification_scheduler.mark_stale_processing_exhausted",
            return_value=0
        ),
        patch(
            "notification_scheduler.dispatch_claimed_notifications",
            return_value=fake_dispatch_result
        )
    ):
        result = run_notification_cycle(
            notification_type="CONSOLE_TEST_CYCLE",
            limit=1
        )

    assert result["cycle_status"] == "FAILED"
    print("[TEST] PASS: Dispatcher error -> FAILED")


if __name__ == "__main__":
    test_dispatcher_failure()
    test_dispatcher_error()
    print("[TEST] ALL PASS")
