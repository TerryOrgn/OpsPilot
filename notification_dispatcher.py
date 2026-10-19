from db import get_connection

MAX_RETRY_COUNT = 3

def dispatch_pending_notifications(limit=10, notification_type="CONSOLE"):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    n.ID AS NOTIFICATION_ID,
                    n.EVENT_ID,
                    n.ALERT_ID,
                    n.NOTIFICATION_TYPE,
                    n.NOTIFICATION_STATUS,
                    a.EXECUTION_ID,
                    a.JOB_NAME,
                    a.ALERT_TYPE,
                    s.CHANGE_TYPE
                FROM JOB_NOTIFICATION_HISTORY n
                JOIN JOB_ALERT_HISTORY a
                    ON n.ALERT_ID = a.ID
                JOIN JOB_ALERT_STATUS_HISTORY s
                    ON n.EVENT_ID = s.ID
                WHERE n.NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                  AND n.RETRY_COUNT < %s
                  AND n.NOTIFICATION_TYPE = %s
                  AND s.CHANGE_TYPE IN ('CREATE', 'REOPEN')

                ORDER BY n.ID
                LIMIT %s
                """,
                (MAX_RETRY_COUNT, notification_type, limit)
            )

            notifications = cursor.fetchall()

            print(f"[DISPATCHER] 待处理通知数量: {len(notifications)}")

            for notification in notifications:
                notification_id = notification["NOTIFICATION_ID"]

                try:
                    # 模拟通知发送
                    send_console_notification(notification)

                    # 发送成功
                    cursor.execute(
                        """
                        UPDATE JOB_NOTIFICATION_HISTORY
                        SET NOTIFICATION_STATUS = 'SENT',
                            SENT_AT             = CURRENT_TIMESTAMP(3),
                            LAST_ERROR_MESSAGE  = NULL,
                            UPDATED_AT          = CURRENT_TIMESTAMP(3)
                        WHERE ID = %s
                          AND NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                          AND RETRY_COUNT < %s
                        """,
                        (notification_id, MAX_RETRY_COUNT)
                    )

                    updated_rows = cursor.rowcount

                    if updated_rows != 1:
                        raise RuntimeError(
                            f"Notification SENT update failed: "
                            f"ID={notification_id}, UPDATED_ROWS={updated_rows}"
                        )

                    print(
                        f"[DISPATCHER] SENT UPDATE "
                        f"ID={notification_id} "
                        f"UPDATED_ROWS={updated_rows}"
                    )


                except Exception as exc:
                    # 发送失败
                    cursor.execute(
                        """
                        UPDATE JOB_NOTIFICATION_HISTORY
                        SET NOTIFICATION_STATUS = 'FAILED',
                            RETRY_COUNT         = RETRY_COUNT + 1,
                            LAST_ERROR_MESSAGE  = %s,
                            UPDATED_AT          = CURRENT_TIMESTAMP(3)
                        WHERE ID = %s
                          AND NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                          AND RETRY_COUNT < %s
                        """,
                        (str(exc), notification_id, MAX_RETRY_COUNT)
                    )

                    print(
                        f"[DISPATCHER] FAILED "
                        f"ID={notification_id} ERROR={exc}"
                    )

            connection.commit()

    finally:
        connection.close()

def send_console_notification(notification):
    print(
        f"[NOTIFICATION] "
        f"ID={notification['NOTIFICATION_ID']} "
        f"EXECUTION_ID={notification['EXECUTION_ID']} "
        f"JOB_NAME={notification['JOB_NAME']} "
        f"ALERT_TYPE={notification['ALERT_TYPE']} "
        f"EVENT={notification['CHANGE_TYPE']}"
    )

if __name__ == "__main__":
    dispatch_pending_notifications()