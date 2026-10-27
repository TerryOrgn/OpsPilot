
from db import get_connection
from notification_claim import claim_notifications

TEST_ID = 23
TEST_TYPE = "CONSOLE_TEST_EXHAUSTION"


def main():
    print("[TEST] 开始 EXHAUSTED 领取保护测试")

    notifications = claim_notifications(
        limit=10,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 0, (
        f"预期领取 0 条，实际领取 {len(notifications)} 条"
    )

    print("[TEST] PASS：EXHAUSTED 通知未被领取")

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    NOTIFICATION_STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    PROCESSING_STARTED_AT
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
    assert row["NOTIFICATION_STATUS"] == "EXHAUSTED"
    assert row["RETRY_COUNT"] == 3
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None

    print("[TEST] PASS：状态仍为 EXHAUSTED")
    print("[TEST] PASS：RETRY_COUNT 未变化")
    print("[TEST] PASS：Claim Token 未生成")
    print("[TEST] EXHAUSTED 领取保护测试全部通过")


if __name__ == "__main__":
    main()
