
from notification_claim import claim_notifications

TEST_ID = 22
TEST_TYPE = "CONSOLE_TEST_RECOVERY_E2E"


def main():
    notifications = claim_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 1, (
        f"预期领取 1 条通知，实际 {len(notifications)} 条"
    )

    notification = notifications[0]

    assert notification["NOTIFICATION_ID"] == TEST_ID
    assert notification["CLAIM_TOKEN"]

    print(f"[TEST] PASS：领取通知 ID={TEST_ID}")
    print(f"[TEST] Token A={notification['CLAIM_TOKEN']}")
    print("[TEST] Recovery E2E 第一阶段通过")


if __name__ == "__main__":
    main()
