
from unittest.mock import patch

from db import get_connection
from notification_dispatcher import dispatch_claimed_notifications
from notification_confirmation import confirm_notification_sent

TEST_ID = 22
TEST_TYPE = "CONSOLE_TEST_RECOVERY_E2E"

OLD_TOKEN = "e1655a69-983d-4a37-887a-7315da5b21f5"

captured_tokens = []


def capture_confirm(notification_id, claim_token):
    if notification_id == TEST_ID:
        captured_tokens.append(claim_token)

    return confirm_notification_sent(
        notification_id=notification_id,
        claim_token=claim_token
    )


def main():
    print("[TEST] 开始 Recovery E2E 最终阶段")

    with patch(
        "notification_dispatcher.confirm_notification_sent",
        side_effect=capture_confirm
    ):
        stats = dispatch_claimed_notifications(
            limit=1,
            notification_type=TEST_TYPE
        )

    assert stats == {
        "claimed": 1,
        "sent": 1,
        "failed": 0,
        "errors": 0
    }, f"批次统计异常: {stats}"

    assert len(captured_tokens) == 1
    new_token = captured_tokens[0]

    assert new_token != OLD_TOKEN, "重新领取后 Token 未更新"

    print("[TEST] PASS：Token B 与 Token A 不同")
    print(f"[TEST] Token B={new_token}")

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

    assert row is not None
    assert row["NOTIFICATION_STATUS"] == "SENT"
    assert row["RETRY_COUNT"] == 1
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None
    assert row["SENT_AT"] is not None
    assert row["LAST_ERROR_MESSAGE"] is None

    print("[TEST] PASS：最终状态为 SENT")
    print("[TEST] PASS：RETRY_COUNT 保持为 1")
    print("[TEST] PASS：Claim Token 已清空")
    print("[TEST] PASS：发送时间已记录")
    print("[TEST] PASS：历史超时错误已清空")
    print("[TEST] Recovery E2E 全链路测试通过")


if __name__ == "__main__":
    main()
