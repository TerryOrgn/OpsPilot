from uuid import UUID

from notification_claim import claim_notifications


def main():
    print("[TEST] 开始 Claim Token 测试")

    notifications = claim_notifications(
        limit=1,
        notification_type="CONSOLE_TEST_TOKEN"
    )

    assert len(notifications) == 1, (
        f"预期领取 1 条，实际领取 {len(notifications)} 条"
    )

    notification = notifications[0]

    notification_id = notification["NOTIFICATION_ID"]
    claim_token = notification["CLAIM_TOKEN"]

    # 验证返回的 Token 是合法 UUID
    UUID(claim_token)

    print(f"[TEST] NOTIFICATION_ID={notification_id}")
    print(f"[TEST] CLAIM_TOKEN={claim_token}")

    # 再次领取，验证不会重复领取
    second = claim_notifications(
        limit=1,
        notification_type="CONSOLE_TEST_TOKEN"
    )

    assert len(second) == 0

    print("[TEST] PASS：Claim Token 生成成功，且未重复领取")


if __name__ == "__main__":
    main()