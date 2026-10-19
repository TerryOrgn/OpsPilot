from unittest.mock import patch

import notification_dispatcher


TEST_NOTIFICATION_ID = 5
TEST_NOTIFICATION_TYPE = "CONSOLE_TEST_MAX_RETRY"


def simulate_send_failure(notification):
    notification_id = notification["NOTIFICATION_ID"]

    if notification_id != TEST_NOTIFICATION_ID:
        raise AssertionError(
            f"Unexpected notification ID: {notification_id}"
        )

    print(f"[TEST] 模拟发送失败: ID={notification_id}")

    raise RuntimeError("Simulated max retry failure")


def main():
    print("[TEST] 开始最大重试次数测试")

    with patch.object(
        notification_dispatcher,
        "send_console_notification",
        side_effect=simulate_send_failure,
    ):
        for attempt in range(1, 5):
            print(f"\n========== 第 {attempt} 次调度 ==========")

            notification_dispatcher.dispatch_pending_notifications(
                limit=10,
                notification_type=TEST_NOTIFICATION_TYPE,
            )

    print("\n[TEST] 最大重试次数测试结束")


if __name__ == "__main__":
    main()