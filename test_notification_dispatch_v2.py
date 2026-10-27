
from db import get_connection
from notification_dispatcher import dispatch_claimed_notifications

TEST_ID = 15
TEST_TYPE = "CONSOLE_TEST_DISPATCH_V2"


def main():
    print("[TEST] 开始 Dispatcher V2 端到端测试")

    # 执行领取、发送和成功确认
    dispatch_claimed_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    # 查询数据库最终状态
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    NOTIFICATION_STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    PROCESSING_STARTED_AT,
                    SENT_AT,
                    LAST_ERROR_MESSAGE
                FROM JOB_NOTIFICATION_HISTORY
                WHERE ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (TEST_ID, TEST_TYPE)
            )

            row = cursor.fetchone()
    finally:
        connection.close()

    assert row is not None, "测试通知不存在"
    assert row["NOTIFICATION_STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 0
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None
    assert row["SENT_AT"] is not None
    assert row["LAST_ERROR_MESSAGE"] is None

    print("[TEST] PASS：通知状态为 SENT")
    print("[TEST] PASS：Claim Token 已清空")
    print("[TEST] PASS：SENT_AT 已记录")
    print("[TEST] Dispatcher V2 端到端测试全部通过")


if __name__ == "__main__":
    main()
