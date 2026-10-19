from datetime import datetime
from db import get_connection


def save_alert(job, alert_type, alert_level, alert_message):
    """
    保存 JOB 告警。

    返回：
        CREATED   - 首次创建
        DUPLICATE - 已有未恢复告警
        REOPENED  - 已恢复告警重新打开
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            now = datetime.now()

            execution_id = job["EXECUTION_ID"]

            # 1. 查询已有告警并加锁
            cursor.execute(
                """
                SELECT ID, ALERT_STATUS
                FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                  AND ALERT_TYPE = %s
                FOR UPDATE
                """,
                (execution_id, alert_type)
            )

            existing = cursor.fetchone()

            if existing is None:

                # 2. 首次创建告警
                cursor.execute(
                    """
                    INSERT INTO JOB_ALERT_HISTORY (
                        EXECUTION_ID,
                        SYSTEM_ID,
                        JOB_NAME,
                        ALERT_TYPE,
                        ALERT_LEVEL,
                        ALERT_MESSAGE,
                        ALERT_STATUS,
                        FIRST_DETECTED_AT,
                        LAST_DETECTED_AT,
                        DETECT_COUNT
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, 'OPEN', %s, %s, 1
                    )
                    """,
                    (
                        execution_id,
                        job["SYSTEM_ID"],
                        job["JOB_NAME"],
                        alert_type,
                        alert_level,
                        alert_message,
                        now,
                        now
                    )
                )

                alert_id = cursor.lastrowid
                event_type = "CREATED"

                # 首次创建审计
                cursor.execute(
                    """
                    INSERT INTO JOB_ALERT_STATUS_HISTORY (
                        ALERT_ID,
                        OLD_STATUS,
                        NEW_STATUS,
                        CHANGE_TYPE,
                        CHANGE_REASON,
                        OPERATOR_TYPE,
                        OPERATOR_ID
                    )
                    VALUES (
                        %s, NULL, 'OPEN',
                        'CREATE', %s,
                        'SYSTEM', 'OpsPilot'
                    )
                    """,
                    (
                        alert_id,
                        f"首次检测到异常：{alert_type}"
                    )
                )

                # 获取本次审计事件ID
                event_id = cursor.lastrowid

                # 创建通知任务
                cursor.execute(
                    """
                    INSERT INTO JOB_NOTIFICATION_HISTORY (EVENT_ID,
                                                          ALERT_ID,
                                                          NOTIFICATION_TYPE,
                                                          NOTIFICATION_STATUS)
                    VALUES (%s, %s, 'CONSOLE', 'PENDING')
                    """,
                    (
                        event_id,
                        alert_id
                    )
                )

            else:

                alert_id = existing["ID"]
                old_status = existing["ALERT_STATUS"]

                if old_status == "RESOLVED":

                    # 3. 已恢复告警重新打开
                    cursor.execute(
                        """
                        UPDATE JOB_ALERT_HISTORY
                        SET ALERT_STATUS      = 'OPEN',
                            ALERT_LEVEL       = %s,
                            ALERT_MESSAGE     = %s,
                            LAST_DETECTED_AT  = %s,
                            DETECT_COUNT      = DETECT_COUNT + 1,
                            RESOLVED_AT       = NULL,
                            RESOLUTION_TYPE   = NULL,
                            RESOLUTION_REASON = NULL
                        WHERE ID = %s
                        """,
                        (
                            alert_level,
                            alert_message,
                            now,
                            alert_id
                        )
                    )

                    event_type = "REOPENED"

                    cursor.execute(
                        """
                        INSERT INTO JOB_ALERT_STATUS_HISTORY (
                            ALERT_ID,
                            OLD_STATUS,
                            NEW_STATUS,
                            CHANGE_TYPE,
                            CHANGE_REASON,
                            OPERATOR_TYPE,
                            OPERATOR_ID
                        )
                        VALUES (
                            %s, 'RESOLVED', 'OPEN',
                            'REOPEN', %s,
                            'SYSTEM', 'OpsPilot'
                        )
                        """,
                        (
                            alert_id,
                            f"异常再次出现：{alert_type}"
                        )
                    )

                    # 获取本次 REOPEN 审计事件ID
                    event_id = cursor.lastrowid

                    # 创建新的通知任务
                    cursor.execute(
                        """
                        INSERT INTO JOB_NOTIFICATION_HISTORY (EVENT_ID,
                                                              ALERT_ID,
                                                              NOTIFICATION_TYPE,
                                                              NOTIFICATION_STATUS)
                        VALUES (%s, %s, 'CONSOLE', 'PENDING')
                        """,
                        (event_id, alert_id)
                    )

                else:

                    # 4. OPEN / ACKNOWLEDGED 重复检测
                    cursor.execute(
                        """
                        UPDATE JOB_ALERT_HISTORY
                        SET ALERT_LEVEL      = %s,
                            ALERT_MESSAGE    = %s,
                            LAST_DETECTED_AT = %s,
                            DETECT_COUNT     = DETECT_COUNT + 1
                        WHERE ID = %s
                        """,
                        (
                            alert_level,
                            alert_message,
                            now,
                            alert_id
                        )
                    )

                    event_type = "DUPLICATE"

        # 5. 事务提交
        connection.commit()

        return {
            "alert_id": alert_id,
            "event_type": event_type
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def resolve_alert(execution_id, alert_type, reason):
    """
    自动恢复 JOB 告警，并写入审计记录。

    返回：
        True  - 状态成功变更
        False - 告警不存在或已经恢复
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            # 1. 查询告警并锁定记录
            select_sql = """
                SELECT
                    ID,
                    ALERT_STATUS
                FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                  AND ALERT_TYPE = %s
                FOR UPDATE
            """

            cursor.execute(
                select_sql,
                (execution_id, alert_type)
            )

            alert = cursor.fetchone()

            if alert is None:
                connection.rollback()
                return False

            old_status = alert["ALERT_STATUS"]

            # 已经恢复，不需要重复处理
            if old_status == "RESOLVED":
                connection.rollback()
                return False

            if old_status not in ("OPEN", "ACKNOWLEDGED"):
                connection.rollback()
                return False

            alert_id = alert["ID"]

            # 2. 更新告警状态
            update_sql = """
                UPDATE JOB_ALERT_HISTORY
                SET
                    ALERT_STATUS = 'RESOLVED',
                    RESOLVED_AT = CURRENT_TIMESTAMP(3),
                    RESOLUTION_TYPE = 'AUTO',
                    RESOLUTION_REASON = %s
                WHERE ID = %s
            """

            cursor.execute(
                update_sql,
                (reason, alert_id)
            )

            # 3. 写入状态变更审计
            audit_sql = """
                INSERT INTO JOB_ALERT_STATUS_HISTORY (
                    ALERT_ID,
                    OLD_STATUS,
                    NEW_STATUS,
                    CHANGE_TYPE,
                    CHANGE_REASON,
                    OPERATOR_TYPE,
                    OPERATOR_ID
                )
                VALUES (
                    %s, %s, 'RESOLVED',
                    'AUTO_RESOLVE', %s,
                    'SYSTEM', 'OpsPilot'
                )
            """

            cursor.execute(
                audit_sql,
                (
                    alert_id,
                    old_status,
                    reason
                )
            )


        # 4. 同一事务提交
        connection.commit()

        return True

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()