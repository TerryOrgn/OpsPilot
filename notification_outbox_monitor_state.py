
from db import get_connection


VALID_STATUSES = {"NORMAL", "ACTION_REQUIRED"}


def transition_outbox_monitor_state(
    notification_type,
    new_status
):
    if (
        not isinstance(notification_type, str)
        or not notification_type.strip()
        or len(notification_type) > 30
    ):
        raise ValueError("Invalid notification_type")

    if new_status not in VALID_STATUSES:
        raise ValueError("Invalid new_status")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            # 确保该通知类型存在状态记录
            cursor.execute(
                """
                INSERT INTO JOB_OUTBOX_MONITOR_STATE
                    (NOTIFICATION_TYPE, EXHAUSTED_STATUS)
                VALUES (%s, 'NORMAL')
                ON DUPLICATE KEY UPDATE
                    NOTIFICATION_TYPE = NOTIFICATION_TYPE
                """,
                (notification_type,)
            )

            # 锁定状态记录，避免并发重复转换
            cursor.execute(
                """
                SELECT EXHAUSTED_STATUS
                FROM JOB_OUTBOX_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
                FOR UPDATE
                """,
                (notification_type,)
            )

            row = cursor.fetchone()

            old_status = (
                row["EXHAUSTED_STATUS"]
                if isinstance(row, dict)
                else row[0]
            )

            changed = old_status != new_status

            if changed:
                # 1. 更新监控状态
                cursor.execute(
                    """
                    UPDATE JOB_OUTBOX_MONITOR_STATE
                    SET EXHAUSTED_STATUS = %s
                    WHERE NOTIFICATION_TYPE = %s
                    """,
                    (new_status, notification_type)
                )

                # 2. 在同一个事务中记录待处理告警
                cursor.execute(
                    """
                    INSERT INTO JOB_OUTBOX_FALLBACK_ALERT
                    (NOTIFICATION_TYPE,
                     OLD_STATUS,
                     NEW_STATUS,
                     STATUS)
                    VALUES (%s, %s, %s, 'PENDING')
                    """,
                    (
                        notification_type,
                        old_status,
                        new_status
                    )
                )

        conn.commit()

        return {
            "notification_type": notification_type,
            "old_status": old_status,
            "new_status": new_status,
            "changed": changed
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
