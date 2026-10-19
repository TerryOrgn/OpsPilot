from unittest.mock import patch

import notification_dispatcher


TEST_NOTIFICATION_ID = 4
ERROR_MESSAGE = "Simulated notification send failure"


def simulate_send_failure(notification):
    notification_id = notification["NOTIFICATION_ID"]

    if notification_id != TEST_NOTIFICATION_ID:
        raise AssertionError(
            f"Unexpected notification ID: {notification_id}"
        )

    print(
        f"[TEST] 模拟通知发送失败: ID={notification_id}"
    )

    raise RuntimeError(ERROR_MESSAGE)


def main():
    print("[TEST] 开始通知失败测试")

    with patch.object(
        notification_dispatcher,
        "send_console_notification",
        side_effect=simulate_send_failure,
    ):
        notification_dispatcher.dispatch_pending_notifications(
            limit=10,
            notification_type="CONSOLE_TEST_FAIL",
        )

    print("[TEST] 故障注入执行结束，请检查数据库")


if __name__ == "__main__":
    main()