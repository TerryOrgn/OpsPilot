
from db import get_connection
from notification_claim import claim_notifications
from notification_recovery import recover_stale_notifications


TEST_NOTIFICATION_ID = 10
TEST_TYPE = "CONSOLE_TEST_RECOVERY"


def main():
    print("[TEST] 开始 PROCESSING 超时恢复测试")

    # 1. 领取通知
    notifications = claim_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    assert len(notifications) == 1

    notification = notifications[0]

    assert notification["NOTIFICATION_ID"] == TEST_NOTIFICATION_ID

    old_token = notification["CLAIM_TOKEN"]

    print(f"[TEST] CLAIM_TOKEN={old_token}")

    # 2. 模拟处理时间已经超过 300 秒
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET PROCESSING_STARTED_AT =
                    DATE_SUB(CURRENT_TIMESTAMP(3), INTERVAL 600 SECOND)
                WHERE ID = %s
                  AND NOTIFICATION_STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
                """,
                (TEST_NOTIFICATION_ID, old_token)
            )

            assert cursor.rowcount == 1

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    print("[TEST] 已模拟 PROCESSING 超时 600 秒")

    # 3. 执行超时恢复
    recovered_count = recover_stale_notifications(
        notification_type=TEST_TYPE
    )

    assert recovered_count == 1

    print("[TEST] PASS：超时通知恢复成功")


if __name__ == "__main__":
    main()
