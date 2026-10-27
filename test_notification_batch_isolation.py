
from unittest.mock import patch

from db import get_connection
from notification_dispatcher import dispatch_claimed_notifications
from notification_confirmation import confirm_notification_sent

TEST_TYPE = "CONSOLE_TEST_BATCH_ISOLATION"
TEST_IDS = [18, 19, 20, 21]
ERROR_ID = 19


def mock_confirm_sent(notification_id, claim_token):
    if notification_id == ERROR_ID:
        raise RuntimeError("Simulated batch confirmation failure")

    return confirm_notification_sent(
        notification_id=notification_id,
        claim_token=claim_token
    )


def main():
    print("[TEST] 开始 Dispatcher V2 批量异常隔离测试")

    with patch(
        "notification_dispatcher.confirm_notification_sent",
        side_effect=mock_confirm_sent
    ), patch(
        "notification_dispatcher.confirm_notification_failed"
    ) as failed_mock:

        stats = dispatch_claimed_notifications(
            limit=4,
            notification_type=TEST_TYPE
        )

        failed_mock.assert_not_called()

    assert stats == {
        "claimed": 4,
        "sent": 3,
        "failed": 0,
        "errors": 1
    }, f"批次统计不符合预期: {stats}"

    print("[TEST] PASS：批次统计正确")
    print("[TEST] PASS：未错误调用失败确认")

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ID,
                    NOTIFICATION_STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    PROCESSING_STARTED_AT,
                    SENT_AT
                FROM JOB_NOTIFICATION_HISTORY
                WHERE NOTIFICATION_TYPE = %s
                ORDER BY ID
                """,
                (TEST_TYPE,)
            )

            rows = cursor.fetchall()

    finally:
        connection.close()

    assert [row["ID"] for row in rows] == TEST_IDS, (
        f"测试通知 ID 不符合预期: {rows}"
    )

    for row in rows:
        notification_id = row["ID"]

        assert row["RETRY_COUNT"] == 0

        if notification_id == ERROR_ID:
            assert row["NOTIFICATION_STATUS"] == "PROCESSING"
            assert row["CLAIM_TOKEN"] is not None
            assert row["PROCESSING_STARTED_AT"] is not None
            assert row["SENT_AT"] is None
        else:
            assert row["NOTIFICATION_STATUS"] == "SENT"
            assert row["CLAIM_TOKEN"] is None
            assert row["PROCESSING_STARTED_AT"] is None
            assert row["SENT_AT"] is not None

        print(
            f"[TEST] PASS：ID={notification_id} "
            f"STATUS={row['NOTIFICATION_STATUS']}"
        )

    print("[TEST] Dispatcher V2 批量异常隔离测试全部通过")


if __name__ == "__main__":
    main()
