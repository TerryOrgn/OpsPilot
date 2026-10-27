
from unittest.mock import patch

from db import get_connection
from notification_dispatcher import dispatch_claimed_notifications

TEST_ID = 17
TEST_TYPE = "CONSOLE_TEST_CONFIRM_DB_ERROR"


def mock_confirm_error(notification_id, claim_token):
    raise RuntimeError("Simulated database confirmation failure")


def main():
    print("[TEST] 开始数据库确认异常测试")

    with patch(
        "notification_dispatcher.confirm_notification_sent",
        side_effect=mock_confirm_error
    ), patch(
        "notification_dispatcher.confirm_notification_failed"
    ) as failed_mock:

        try:
            dispatch_claimed_notifications(
                limit=1,
                notification_type=TEST_TYPE
            )
        except RuntimeError as exc:
            assert str(exc) == "Simulated database confirmation failure"
            print("[TEST] PASS：数据库确认异常正确向上抛出")
        else:
            raise AssertionError("预期数据库确认异常，但未抛出")

        # 确保没有误调用失败确认
        failed_mock.assert_not_called()
        print("[TEST] PASS：未错误调用失败确认")

    # 检查数据库状态
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
                    SENT_AT
                FROM JOB_NOTIFICATION_HISTORY
                WHERE ID = %s
                  AND NOTIFICATION_TYPE = %s
                """,
                (TEST_ID, TEST_TYPE)
            )

            row = cursor.fetchone()

    finally:
        connection.close()

    assert row is not None
    assert row["NOTIFICATION_STATUS"] == "PROCESSING"
    assert row["RETRY_COUNT"] == 0
    assert row["CLAIM_TOKEN"] is not None
    assert row["PROCESSING_STARTED_AT"] is not None
    assert row["SENT_AT"] is None

    print("[TEST] PASS：数据库仍保持 PROCESSING")
    print("[TEST] PASS：RETRY_COUNT 未增加")
    print("[TEST] PASS：Claim Token 保留")
    print("[TEST] 数据库确认异常测试全部通过")


if __name__ == "__main__":
    main()
