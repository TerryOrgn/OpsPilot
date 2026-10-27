
from db import get_connection

MAX_RETRY_COUNT = 3


def mark_exhausted_notifications(notification_type):
    """
    将已达到重试上限的 FAILED 通知标记为 EXHAUSTED。
    不处理仍处于 PROCESSING 的通知。
    """
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = 'EXHAUSTED',
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
                WHERE NOTIFICATION_STATUS = 'FAILED'
                  AND NOTIFICATION_TYPE = %s
                  AND RETRY_COUNT >= %s
                """,
                (notification_type, MAX_RETRY_COUNT)
            )

            exhausted_count = cursor.rowcount

        connection.commit()

        print(
            f"[EXHAUSTION] 标记重试耗尽通知数量: "
            f"{exhausted_count}"
        )

        return exhausted_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def mark_stale_processing_exhausted(notification_type):
    """
    将超过处理超时阈值、且重试次数已经耗尽的
    PROCESSING 通知转换为 EXHAUSTED。
    """
    from notification_recovery import PROCESSING_TIMEOUT_SECONDS

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = 'EXHAUSTED',
                    CLAIM_TOKEN = NULL,
                    PROCESSING_STARTED_AT = NULL,
                    LAST_ERROR_MESSAGE = 'Processing timeout; retries exhausted',
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
                WHERE NOTIFICATION_STATUS = 'PROCESSING'
                  AND NOTIFICATION_TYPE = %s
                  AND RETRY_COUNT >= %s
                  AND PROCESSING_STARTED_AT <
                      DATE_SUB(
                          CURRENT_TIMESTAMP(3),
                          INTERVAL %s SECOND
                      )
                """,
                (
                    notification_type,
                    MAX_RETRY_COUNT,
                    PROCESSING_TIMEOUT_SECONDS
                )
            )

            exhausted_count = cursor.rowcount

        connection.commit()

        print(
            f"[EXHAUSTION] 超时且重试耗尽通知数量: "
            f"{exhausted_count}"
        )

        return exhausted_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
