
import uuid

from db import get_connection

MAX_RETRIES = 3

def claim_notification(notification_id=None, *, retry_seconds=0):
    """
    原子领取一条待发送通知。

    返回：
        dict - 成功领取的通知任务
        None - 没有待领取任务
    """
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ID, EVENT_ID, ALERT_ID, NOTIFICATION_TYPE
                FROM JOB_NOTIFICATION_HISTORY
                WHERE (%s IS NULL OR ID = %s)
                  AND (NOTIFICATION_STATUS = 'PENDING'
                       OR (NOTIFICATION_STATUS = 'FAILED'
                           AND RETRY_COUNT < %s
                           AND (%s = 0 OR UPDATED_AT <= DATE_SUB(NOW(3), INTERVAL %s SECOND))))
                ORDER BY CREATED_AT, ID LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                (notification_id, notification_id, MAX_RETRIES, retry_seconds, retry_seconds),
            )

            notification = cursor.fetchone()

            if notification is None:
                connection.rollback()
                return None

            claim_token = str(uuid.uuid4())

            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = 'PROCESSING',
                    CLAIM_TOKEN = %s,
                    PROCESSING_STARTED_AT = NOW(3)
                WHERE ID = %s
                  AND (NOTIFICATION_STATUS = 'PENDING'
                       OR (NOTIFICATION_STATUS = 'FAILED'
                           AND RETRY_COUNT < %s))
                """,
                (claim_token, notification["ID"], MAX_RETRIES),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Notification claim update failed"
                )

        connection.commit()

        notification["CLAIM_TOKEN"] = claim_token
        return notification

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def complete_notification(
    notification_id,
    claim_token,
    success,
    error_message=None,
):
    """
    确认通知发送结果。

    仅允许持有正确 CLAIM_TOKEN 的 Worker
    更新 PROCESSING 状态的通知。

    返回：
        True  - 状态更新成功
        False - 状态不匹配或任务不存在
    """
    if not claim_token:
        raise ValueError("claim_token must not be empty")

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            if success:
                cursor.execute(
                    """
                    UPDATE JOB_NOTIFICATION_HISTORY
                    SET NOTIFICATION_STATUS = 'SENT',
                        SENT_AT = NOW(3),
                        LAST_ERROR_MESSAGE = NULL,
                        CLAIM_TOKEN = NULL,
                        PROCESSING_STARTED_AT = NULL
                    WHERE ID = %s
                      AND NOTIFICATION_STATUS = 'PROCESSING'
                      AND CLAIM_TOKEN = %s
                    """,
                    (notification_id, claim_token),
                )
            else:
                cursor.execute(
                    """
                    UPDATE JOB_NOTIFICATION_HISTORY
                        SET NOTIFICATION_STATUS = CASE
                            WHEN RETRY_COUNT + 1 >= 3 THEN 'EXHAUSTED'
                            ELSE 'FAILED'
                        END,
                        RETRY_COUNT = RETRY_COUNT + 1,
                        LAST_ERROR_MESSAGE = %s,
                        CLAIM_TOKEN = NULL,
                        PROCESSING_STARTED_AT = NULL
                    WHERE ID = %s
                      AND NOTIFICATION_STATUS = 'PROCESSING'
                      AND CLAIM_TOKEN = %s
                    """,
                    (
                        (error_message or "Unknown error")[:1000],
                        notification_id,
                        claim_token,
                    ),
                )

            updated = cursor.rowcount == 1

        connection.commit()
        return updated

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def send_console_notification(notification_id=None, *, retry_seconds=0):
    """
    领取并发送一条 CONSOLE 通知。

    返回：
        True  - 成功发送并确认
        False - 没有可领取任务

    发送异常会记录 FAILED 并重新抛出。
    """
    task = claim_notification(notification_id, retry_seconds=retry_seconds)

    if task is None:
        return False

    task_id = task["ID"]
    token = task["CLAIM_TOKEN"]

    try:
        if task["NOTIFICATION_TYPE"] != "CONSOLE":
            raise ValueError(
                "Unsupported notification type: "
                + task["NOTIFICATION_TYPE"]
            )

        print(
            "[NOTIFICATION] "
            f"event_id={task['EVENT_ID']} "
            f"alert_id={task['ALERT_ID']}"
        )

    except Exception as exc:
        complete_notification(
            task_id,
            token,
            success=False,
            error_message=str(exc),
        )
        raise

    confirmed = complete_notification(
        task_id,
        token,
        success=True,
    )

    if not confirmed:
        raise RuntimeError(
            f"Notification {task_id} sent but confirmation failed"
        )

    return True

