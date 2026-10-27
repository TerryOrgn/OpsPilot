
from notification_confirmation import confirm_notification_sent

NOTIFICATION_ID = 9
CLAIM_TOKEN = "051a42be-62bf-45e5-9003-d1bbe2ed0a78"


def main():
    print("[TEST] 开始正确 Claim Token 测试")

    # 第一次：正确 Token 确认
    result = confirm_notification_sent(
        notification_id=NOTIFICATION_ID,
        claim_token=CLAIM_TOKEN
    )

    assert result is True, "正确 Token 应当确认成功"
    print("[TEST] PASS：正确 Token 确认成功")

    # 第二次：相同 Token 重复确认
    result = confirm_notification_sent(
        notification_id=NOTIFICATION_ID,
        claim_token=CLAIM_TOKEN
    )

    assert result is False, "旧 Token 不应重复确认成功"
    print("[TEST] PASS：旧 Token 重复确认被拒绝")


if __name__ == "__main__":
    main()
