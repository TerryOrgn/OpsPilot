
from db import get_connection
from notification_claim import claim_notifications

TEST_TYPE = "CONSOLE_TEST_BATCH_CLAIM"
EXPECTED_IDS = {12, 13}


def main():
    print("[TEST] 开始批量 Claim 测试")

    # 1. 一次领取两条通知
    notifications = claim_notifications(
        limit=2,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 2, (
        f"预期领取 2 条，实际 {len(notifications)} 条"
    )

    actual_ids = {
        n["NOTIFICATION_ID"] for n in notifications
    }
    assert actual_ids == EXPECTED_IDS

    # 2. 检查 Token 唯一性和发送所需字段
    tokens = []

    for notification in notifications:
        notification_id = notification["NOTIFICATION_ID"]
        token = notification["CLAIM_TOKEN"]

        assert token, f"ID={notification_id} 缺少 Token"

        for field in (
            "EXECUTION_ID",
            "JOB_NAME",
            "ALERT_TYPE",
            "CHANGE_TYPE",
        ):
            assert field in notification, (
                f"ID={notification_id} 缺少字段 {field}"
            )

        tokens.append(token)
        print(f"[TEST] ID={notification_id} TOKEN={token}")

    assert len(set(tokens)) == 2, "两条通知的 Token 必须不同"

    # 3. 再次领取，应该返回 0 条
    second_claim = claim_notifications(
        limit=2,
        notification_type=TEST_TYPE
    )

    assert len(second_claim) == 0, "不应重复领取 PROCESSING 通知"

    # 4. 检查数据库中的状态与 Token
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ID,
                    NOTIFICATION_STATUS,
                    CLAIM_TOKEN,
                    PROCESSING_STARTED_AT
                FROM JOB_NOTIFICATION_HISTORY
                WHERE NOTIFICATION_TYPE = %s
                ORDER BY ID
                """,
                (TEST_TYPE,)
            )

            rows = cursor.fetchall()

    finally:
        connection.close()

    assert len(rows) == 2

    token_by_id = {
        n["NOTIFICATION_ID"]: n["CLAIM_TOKEN"]
        for n in notifications
    }

    for row in rows:
        notification_id = row["ID"]

        assert row["NOTIFICATION_STATUS"] == "PROCESSING"
        assert row["CLAIM_TOKEN"] == token_by_id[notification_id]
        assert row["PROCESSING_STARTED_AT"] is not None

    print("[TEST] PASS：两条通知成功领取")
    print("[TEST] PASS：Claim Token 唯一且与数据库一致")
    print("[TEST] PASS：发送所需字段完整")
    print("[TEST] PASS：重复领取返回 0 条")
    print("[TEST] 批量 Claim 测试全部通过")


if __name__ == "__main__":
    main()
