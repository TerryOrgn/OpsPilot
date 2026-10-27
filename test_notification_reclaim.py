
from notification_claim import claim_notifications
from notification_confirmation import confirm_notification_sent


TEST_NOTIFICATION_ID = 10
TEST_TYPE = "CONSOLE_TEST_RECOVERY"

OLD_TOKEN = "01c21564-6e9f-4543-89e8-911cba8c88a7"


def main():
    print("[TEST] 开始超时恢复后的重新领取测试")

    # 1. 使用旧 Token 尝试确认
    result = confirm_notification_sent(
        notification_id=TEST_NOTIFICATION_ID,
        claim_token=OLD_TOKEN
    )

    assert result is False, "旧 Token 不应确认成功"

    print("[TEST] PASS：旧 Token 已失效")

    # 2. 重新领取 FAILED 通知
    notifications = claim_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 1

    notification = notifications[0]

    assert notification["NOTIFICATION_ID"] == TEST_NOTIFICATION_ID

    new_token = notification["CLAIM_TOKEN"]

    # 3. 验证重新领取生成了不同的 Token
    assert new_token != OLD_TOKEN

    print(f"[TEST] OLD_TOKEN={OLD_TOKEN}")
    print(f"[TEST] NEW_TOKEN={new_token}")

    # 4. 再次使用旧 Token 尝试确认
    result = confirm_notification_sent(
        notification_id=TEST_NOTIFICATION_ID,
        claim_token=OLD_TOKEN
    )

    assert result is False, "旧 Token 不应影响新的领取者"

    print("[TEST] PASS：重新领取后旧 Token 仍无法确认")
    print("[TEST] PASS：超时恢复与重新领取验证成功")


if __name__ == "__main__":
    main()
