
from db import get_connection
from notification_claim import claim_notifications
from notification_confirmation import confirm_notification_failed

TEST_ID = 11
TEST_TYPE = "CONSOLE_TEST_CONFIRM_FAILED"


def main():
    print("[TEST] 开始失败确认测试")

    # 1. 领取通知
    notifications = claim_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 1, "应领取到一条通知"

    notification = notifications[0]
    assert notification["NOTIFICATION_ID"] == TEST_ID

    token = notification["CLAIM_TOKEN"]
    assert token, "Claim Token 不应为空"

    print(f"[TEST] CLAIM_TOKEN={token}")

    # 2. 使用正确 Token 确认失败
    result = confirm_notification_failed(
        notification_id=TEST_ID,
        claim_token=token,
        error_message="Simulated notification send failure"
    )

    assert result is True, "正确 Token 应确认失败成功"
    print("[TEST] PASS：正确 Token 失败确认成功")

    # 3. 重复确认应被拒绝
    result = confirm_notification_failed(
        notification_id=TEST_ID,
        claim_token=token,
        error_message="Duplicate failure confirmation"
    )

    assert result is False, "重复确认应被拒绝"
    print("[TEST] PASS：重复失败确认被拒绝")

    # 4. 检查数据库最终状态
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT NOTIFICATION_STATUS,
                       RETRY_COUNT,
                       CLAIM_TOKEN,
                       PROCESSING_STARTED_AT,
                       LAST_ERROR_MESSAGE
                FROM JOB_NOTIFICATION_HISTORY
                WHERE ID = %s
                """,
                (TEST_ID,)
            )
            row = cursor.fetchone()
    finally:
        connection.close()

    # 兼容字典游标
    assert row["NOTIFICATION_STATUS"] == "FAILED"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None
    assert row["LAST_ERROR_MESSAGE"] == "Simulated notification send failure"

    print("[TEST] PASS：数据库状态及失败次数正确")
    print("[TEST] 全部测试通过")


if __name__ == "__main__":
    main()
