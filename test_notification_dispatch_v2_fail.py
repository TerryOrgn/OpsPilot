
from unittest.mock import patch

from db import get_connection
from notification_dispatcher import dispatch_claimed_notifications

TEST_ID = 16
TEST_TYPE = "CONSOLE_TEST_DISPATCH_V2_FAIL"
ERROR_MESSAGE = "Simulated console send failure"


def mock_send_failure(notification):
    raise RuntimeError(ERROR_MESSAGE)


def main():
    print("[TEST] 开始 Dispatcher V2 发送失败测试")

    # 只模拟发送失败，保留真实的 Claim 和数据库确认逻辑
    with patch(
        "notification_dispatcher.send_console_notification",
        side_effect=mock_send_failure
    ):
        dispatch_claimed_notifications(
            limit=1,
            notification_type=TEST_TYPE
        )

    # 验证数据库最终状态
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
    assert row["NOTIFICATION_STATUS"] == "FAILED"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None
    assert row["SENT_AT"] is None
    assert row["LAST_ERROR_MESSAGE"] == ERROR_MESSAGE

    print("[TEST] PASS：发送失败后状态为 FAILED")
    print("[TEST] PASS：RETRY_COUNT 仅增加一次")
    print("[TEST] PASS：Claim Token 已清空")
    print("[TEST] PASS：失败原因正确记录")
    print("[TEST] Dispatcher V2 发送失败测试全部通过")


if __name__ == "__main__":
    main()
