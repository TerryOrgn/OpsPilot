from db import get_connection
from uuid import uuid4

MAX_RETRY_COUNT = 3


def claim_notifications(limit=10, notification_type="CONSOLE"):
    connection = get_connection()

    try:
        # 显式开启事务，确保 SELECT 锁与 UPDATE 属于同一事务
        connection.begin()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    n.ID AS NOTIFICATION_ID,
                    n.EVENT_ID,
                    n.ALERT_ID,
                    n.NOTIFICATION_TYPE,
                    n.RETRY_COUNT
                FROM JOB_NOTIFICATION_HISTORY n
                JOIN JOB_ALERT_STATUS_HISTORY s
                    ON n.EVENT_ID = s.ID
                WHERE n.NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                  AND n.RETRY_COUNT < %s
                  AND n.NOTIFICATION_TYPE = %s
                  AND s.CHANGE_TYPE IN ('CREATE', 'REOPEN')
                ORDER BY n.ID
                LIMIT %s
                FOR UPDATE OF n SKIP LOCKED
                """,
                (MAX_RETRY_COUNT, notification_type, limit)
            )

            notifications = cursor.fetchall()

            for notification in notifications:
                notification_id = notification["NOTIFICATION_ID"]

                for notification in notifications:
                    notification_id = notification["NOTIFICATION_ID"]

                    # 每次领取都生成新的唯一令牌
                    claim_token = str(uuid4())

                    cursor.execute(
                        """
                        UPDATE JOB_NOTIFICATION_HISTORY
                        SET NOTIFICATION_STATUS   = 'PROCESSING',
                            PROCESSING_STARTED_AT = CURRENT_TIMESTAMP(3),
                            CLAIM_TOKEN           = %s,
                            UPDATED_AT            = CURRENT_TIMESTAMP(3)
                        WHERE ID = %s
                          AND NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                          AND RETRY_COUNT < %s
                        """,
                        (
                            claim_token,
                            notification_id,
                            MAX_RETRY_COUNT
                        )
                    )

                    if cursor.rowcount != 1:
                        raise RuntimeError(
                            f"Claim failed: ID={notification_id}"
                        )



                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Claim failed: ID={notification_id}"
                    )

                # 将令牌一并返回给调用方
                notification["CLAIM_TOKEN"] = claim_token

            connection.commit()

            print(
                f"[CLAIM] 成功领取通知数量: {len(notifications)}"
            )

            return notifications

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()