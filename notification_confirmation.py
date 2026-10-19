from db import get_connection


def confirm_notification_sent(notification_id, claim_token):
    """
    只有持有正确 Claim Token 的 Dispatcher
    才能将通知从 PROCESSING 更新为 SENT。
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_NOTIFICATION_HISTORY
                SET NOTIFICATION_STATUS = 'SENT',
                    SENT_AT = CURRENT_TIMESTAMP(3),
                    LAST_ERROR_MESSAGE = NULL,
                    CLAIM_TOKEN = NULL,
                    PROCESSING_STARTED_AT = NULL,
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
                WHERE ID = %s
                  AND NOTIFICATION_STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
                """,
                (notification_id, claim_token)
            )

            updated_rows = cursor.rowcount

        connection.commit()

        if updated_rows == 1:
            print(f"[CONFIRM] SENT ID={notification_id}")
            return True

        print(
            f"[CONFIRM] REJECTED ID={notification_id} "
            f"原因：状态不匹配或 Claim Token 无效"
        )
        return False

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()