
from db import get_connection
from notification_exhaustion import mark_exhausted_notifications

TEST_ID = 23
TEST_TYPE = "CONSOLE_TEST_EXHAUSTION"


def main():
    print("[TEST] 开始重试耗尽状态转换测试")

    # 第一次执行：FAILED -> EXHAUSTED
    first_count = mark_exhausted_notifications(
        notification_type=TEST_TYPE
    )

    assert first_count == 1, (
        f"预期更新 1 条，实际更新 {first_count} 条"
    )

    print("[TEST] PASS：首次转换数量为 1")

    # 第二次执行：验证幂等性
    second_count = mark_exhausted_notifications(
        notification_type=TEST_TYPE
    )

    assert second_count == 0, (
        f"预期重复执行更新 0 条，实际更新 {second_count} 条"
    )

    print("[TEST] PASS：重复执行不更新记录")

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
    assert row["NOTIFICATION_STATUS"] == "EXHAUSTED"
    assert row["RETRY_COUNT"] == 3
    assert row["CLAIM_TOKEN"] is None
    assert row["PROCESSING_STARTED_AT"] is None
    assert (
        row["LAST_ERROR_MESSAGE"]
        == "Simulated maximum retry exhaustion"
    )

    print("[TEST] PASS：最终状态为 EXHAUSTED")
    print("[TEST] PASS：RETRY_COUNT 保持为 3")
    print("[TEST] PASS：原始错误信息保留")
    print("[TEST] Exhaustion 状态转换测试全部通过")


if __name__ == "__main__":
    main()
