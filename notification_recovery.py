
from db import get_connection

PROCESSING_TIMEOUT_SECONDS = 300
MAX_RETRY_COUNT = 3

def recover_stale_notifications(notification_type, notification_id=None, timeout_seconds=PROCESSING_TIMEOUT_SECONDS):
    if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = CASE
                        WHEN RETRY_COUNT + 1 >= %s THEN 'EXHAUSTED'
                        ELSE 'FAILED' END,
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
                  AND (%s IS NULL OR ID = %s)
                """,
                (MAX_RETRY_COUNT, notification_type,
                 timeout_seconds,
                 notification_id, notification_id)
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
