from notification_dispatcher import dispatch_pending_notifications


def main():
    print("[TEST] 开始 FAILED → SENT 重试测试")

    dispatch_pending_notifications(
        limit=10,
        notification_type="CONSOLE_TEST_FAIL",
    )

    print("[TEST] 重试测试执行结束")


if __name__ == "__main__":
    main()