
from db import get_connection


def get_dead_letter_state(notification_type):
    conn = get_connection()

    try:
        cursor = conn.cursor()

        try:
            sql = """
                SELECT DEAD_LETTER_STATUS
                FROM JOB_NOTIFICATION_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
            """

            cursor.execute(sql, (notification_type,))
            row = cursor.fetchone()

            if row is None:
                return None

            if isinstance(row, dict):
                return row["DEAD_LETTER_STATUS"]

            return row[0]

        finally:
            cursor.close()

    finally:
        conn.close()



def save_dead_letter_state(notification_type, status):
    if status not in ("NORMAL", "ACTION_REQUIRED"):
        raise ValueError(f"Invalid dead-letter status: {status}")

    conn = get_connection()

    try:
        cursor = conn.cursor()

        try:
            sql = """
                INSERT INTO JOB_NOTIFICATION_MONITOR_STATE
                    (NOTIFICATION_TYPE, DEAD_LETTER_STATUS)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    DEAD_LETTER_STATUS = VALUES(DEAD_LETTER_STATUS),
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
            """

            cursor.execute(sql, (notification_type, status))
            conn.commit()

        finally:
            cursor.close()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def _transition_dead_letter_state_once(notification_type, new_status):

    if new_status not in ("NORMAL", "ACTION_REQUIRED"):
        raise ValueError(f"Invalid dead-letter status: {new_status}")

    conn = get_connection()

    try:
        cursor = conn.cursor()

        try:
            # 确保记录存在。
            # 主键唯一约束负责处理并发首次插入。
            cursor.execute(
                """
                INSERT IGNORE INTO JOB_NOTIFICATION_MONITOR_STATE
                    (NOTIFICATION_TYPE, DEAD_LETTER_STATUS)
                VALUES (%s, %s)
                """,
                (notification_type, new_status)
            )

            # 锁定该通知类型的状态记录。
            cursor.execute(
                """
                SELECT DEAD_LETTER_STATUS
                FROM JOB_NOTIFICATION_MONITOR_STATE
                WHERE NOTIFICATION_TYPE = %s
                FOR UPDATE
                """,
                (notification_type,)
            )

            row = cursor.fetchone()
            old_status = (
                row["DEAD_LETTER_STATUS"]
                if isinstance(row, dict)
                else row[0]
            )

            event = None

            if old_status != new_status:
                if new_status == "ACTION_REQUIRED":
                    event = "DEAD_LETTER_DETECTED"
                else:
                    event = "DEAD_LETTER_CLEARED"

                cursor.execute(
                    """
                    UPDATE JOB_NOTIFICATION_MONITOR_STATE
                    SET DEAD_LETTER_STATUS = %s
                    WHERE NOTIFICATION_TYPE = %s
                    """,
                    (new_status, notification_type)
                )


                # 将状态变化事件写入 Outbox。
                # 与监控状态更新共享同一个数据库事务。
                cursor.execute(
                    """
                    INSERT INTO JOB_MONITOR_EVENT_OUTBOX
                        (NOTIFICATION_TYPE, EVENT_TYPE, STATUS)
                    VALUES (%s, %s, %s)
                    """,
                    (notification_type, event, "PENDING")
                )


            conn.commit()
            return event

        finally:
            cursor.close()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



import time
import pymysql


def transition_dead_letter_state(notification_type, new_status):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            return _transition_dead_letter_state_once(
                notification_type,
                new_status
            )

        except pymysql.err.OperationalError as exc:
            error_code = exc.args[0]

            # 仅重试 MySQL 死锁错误 1213
            if error_code != 1213 or attempt == max_attempts - 1:
                raise

            delay = 0.05 * (2 ** attempt)

            print(
                f"[MONITOR-STATE-RETRY] "
                f"TYPE={notification_type} "
                f"ERROR=DEADLOCK "
                f"ATTEMPT={attempt + 1} "
                f"DELAY={delay}s"
            )

            time.sleep(delay)
