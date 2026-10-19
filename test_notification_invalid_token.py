from notification_confirmation import confirm_notification_sent


def main():
    print("[TEST] 开始错误 Claim Token 测试")

    result = confirm_notification_sent(
        notification_id=9,
        claim_token="invalid-token"
    )

    assert result is False

    print("[TEST] PASS：错误 Token 被拒绝")


if __name__ == "__main__":
    main()