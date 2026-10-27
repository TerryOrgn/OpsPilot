
from db import get_connection

PROCESSING_TIMEOUT_SECONDS = 300
MAX_RETRY_COUNT = 3

def recover_stale_notifications(notification_type):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = 'FAILED',
                    RETRY_COUNT = RETRY_COUNT + 1,
                    LAST_ERROR_MESSAGE = 'Processing timeout',
                    CLAIM_TOKEN = NULL,
                    PROCESSING_STARTED_AT = NULL,
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
                WHERE NOTIFICATION_STATUS = 'PROCESSING'
                  AND NOTIFICATION_TYPE = %s
                  AND PROCESSING_STARTED_AT <
                      DATE_SUB(
                          CURRENT_TIMESTAMP(3),
                          INTERVAL %s SECOND
                      )
                  AND RETRY_COUNT < %s
                """,
                (notification_type,
                 PROCESSING_TIMEOUT_SECONDS,
                 MAX_RETRY_COUNT)
            )

            recovered_count = cursor.rowcount

        connection.commit()

        print(
            f"[RECOVERY] 超时恢复通知数量: {recovered_count}"
        )

        return recovered_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
