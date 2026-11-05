
import os
import uuid

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection
from alert_manager import save_alert, resolve_alert


def main():
    execution_id = "E2E10A_" + uuid.uuid4().hex[:16]
    alert_type = "JOB_FAILED"
    alert_id = None

    job = {
        "EXECUTION_ID": execution_id,
        "SYSTEM_ID": "E2E_TEST",
        "JOB_NAME": "E2E10A_TestJob",
    }

    # 测试前确认数据库
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            assert cursor.fetchone()["db"] == "opspilot_test"

            # 创建测试 JOB，满足外键约束
            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG (
                    EXECUTION_ID,
                    SYSTEM_ID,
                    JOB_NAME,
                    BUSINESS_DATE,
                    START_TIME,
                    END_TIME,
                    STATUS
                )
                VALUES (
                    %s, %s, %s,
                    CURRENT_DATE(),
                    NOW(3), NOW(3), 'FAILED'
                )
                """,
                (
                    execution_id,
                    job["SYSTEM_ID"],
                    job["JOB_NAME"],
                )
            )
        conn.commit()
    finally:
        conn.close()

    try:
        # 1. 创建告警
        result = save_alert(
            job,
            alert_type,
            "CRITICAL",
            "E2E10A simulated failure",
        )

        assert result["event_type"] == "CREATED"
        alert_id = result["alert_id"]

        print("[TEST] ALERT_CREATED=PASS")

        # 2. 自动恢复
        resolved = resolve_alert(
            execution_id,
            alert_type,
            "E2E10A simulated recovery",
        )

        assert resolved is True
        print("[TEST] ALERT_RESOLVED=PASS")

        # 3. 检查审计和通知任务
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        h.ID AS EVENT_ID,
                        h.CHANGE_TYPE,
                        n.ID AS NOTIFICATION_ID,
                        n.NOTIFICATION_STATUS,
                        n.NOTIFICATION_TYPE
                    FROM JOB_ALERT_STATUS_HISTORY h
                    LEFT JOIN JOB_NOTIFICATION_HISTORY n
                        ON n.EVENT_ID = h.ID
                    WHERE h.ALERT_ID = %s
                    ORDER BY h.ID
                    """,
                    (alert_id,)
                )
                rows = cursor.fetchall()
        finally:
            conn.close()

        assert len(rows) == 2, rows

        create_event, resolve_event = rows

        assert create_event["CHANGE_TYPE"] == "CREATE"
        assert create_event["NOTIFICATION_ID"] is not None

        assert resolve_event["CHANGE_TYPE"] == "AUTO_RESOLVE"
        assert resolve_event["NOTIFICATION_ID"] is not None
        assert resolve_event["NOTIFICATION_STATUS"] == "PENDING"
        assert resolve_event["NOTIFICATION_TYPE"] == "CONSOLE"

        print("[TEST] RECOVERY_NOTIFICATION_CREATED=PASS")

        # 4. 重复恢复不得创建新事件
        second_result = resolve_alert(
            execution_id,
            alert_type,
            "Repeated recovery",
        )

        assert second_result is False

        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM JOB_NOTIFICATION_HISTORY
                    WHERE ALERT_ID = %s
                    """,
                    (alert_id,)
                )
                count = cursor.fetchone()["cnt"]
        finally:
            conn.close()

        assert count == 2, count

        print("[TEST] DUPLICATE_RECOVERY_PREVENTED=PASS")
        print("[TEST] ALL PASS: JOB-E2E-10A")

    finally:
        # 仅清理本次唯一测试数据
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_NOTIFICATION_HISTORY
                    WHERE ALERT_ID IN (
                        SELECT ID
                        FROM JOB_ALERT_HISTORY
                        WHERE EXECUTION_ID = %s
                    )
                    """,
                    (execution_id,)
                )

                cursor.execute(
                    """
                    DELETE FROM JOB_ALERT_STATUS_HISTORY
                    WHERE ALERT_ID IN (
                        SELECT ID
                        FROM JOB_ALERT_HISTORY
                        WHERE EXECUTION_ID = %s
                    )
                    """,
                    (execution_id,)
                )

                cursor.execute(
                    """
                    DELETE FROM JOB_ALERT_HISTORY
                    WHERE EXECUTION_ID = %s
                    """,
                    (execution_id,)
                )

                cursor.execute(
                    """
                    DELETE FROM JOB_EXECUTION_LOG
                    WHERE EXECUTION_ID = %s
                    """,
                    (execution_id,)
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


if __name__ == "__main__":
    main()
