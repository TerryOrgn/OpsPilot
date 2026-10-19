from notification_claim import claim_notifications


def main():
    print("[TEST] 第一次领取")

    first = claim_notifications(
        limit=10,
        notification_type="CONSOLE_TEST_CLAIM"
    )

    print(f"[TEST] 第一次领取数量: {len(first)}")

    print("\n[TEST] 第二次领取")

    second = claim_notifications(
        limit=10,
        notification_type="CONSOLE_TEST_CLAIM"
    )

    print(f"[TEST] 第二次领取数量: {len(second)}")


if __name__ == "__main__":
    main()