
from datetime import datetime

from db import get_connection
from pymysql.err import IntegrityError


class WebhookAlertRepository:

    def create_or_update_alert(
            self,
            alert_key,
            alert_type,
            alert_level,
            alert_message,
    ):
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                now = datetime.now()

                # 先尝试插入。
                # 若唯一键已存在，忽略本次插入，
                # 后续锁定已有记录并判断原状态。
                cursor.execute(
                    """
                    INSERT INTO WEBHOOK_METRICS_ALERT (ALERT_KEY,
                                                       ALERT_TYPE,
                                                       ALERT_LEVEL,
                                                       ALERT_MESSAGE,
                                                       ALERT_STATUS,
                                                       FIRST_DETECTED_AT,
                                                       LAST_DETECTED_AT,
                                                       DETECT_COUNT)
                    VALUES (%s, %s, %s, %s,
                            'OPEN', %s, %s, 1) ON DUPLICATE KEY
                    UPDATE
                        ID = ID
                    """,
                    (
                        alert_key,
                        alert_type,
                        alert_level,
                        alert_message,
                        now,
                        now,
                    ),
                )

                # 该 INSERT 只在首次创建时影响一行。
                # 重复键分支为无变化更新。
                created = cursor.rowcount == 1

                cursor.execute(
                    """
                    SELECT ID, ALERT_STATUS, DETECT_COUNT
                    FROM WEBHOOK_METRICS_ALERT
                    WHERE ALERT_KEY = %s
                        FOR UPDATE
                    """,
                    (alert_key,),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Alert not found after insert"
                    )

                alert_id = row["ID"]
                old_status = row["ALERT_STATUS"]

                if created:
                    event_type = "CREATED"

                elif old_status == "RESOLVED":
                    cursor.execute(
                        """
                        UPDATE WEBHOOK_METRICS_ALERT
                        SET ALERT_STATUS      = 'OPEN',
                            ALERT_LEVEL       = %s,
                            ALERT_MESSAGE     = %s,
                            LAST_DETECTED_AT  = %s,
                            DETECT_COUNT      = DETECT_COUNT + 1,
                            RESOLVED_AT       = NULL,
                            RESOLUTION_REASON = NULL
                        WHERE ID = %s
                        """,
                        (
                            alert_level,
                            alert_message,
                            now,
                            alert_id,
                        ),
                    )
                    event_type = "REOPENED"

                elif old_status in ("OPEN", "ACKNOWLEDGED"):
                    cursor.execute(
                        """
                        UPDATE WEBHOOK_METRICS_ALERT
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
                            alert_id,
                        ),
                    )
                    event_type = "DUPLICATE"

                else:
                    raise ValueError(
                        f"Unsupported alert status: {old_status}"
                    )

                cursor.execute(
                    """
                    SELECT ALERT_STATUS, DETECT_COUNT
                    FROM WEBHOOK_METRICS_ALERT
                    WHERE ID = %s
                    """,
                    (alert_id,),
                )

                updated = cursor.fetchone()

                result = {
                    "alert_id": alert_id,
                    "event_type": event_type,
                    "alert_status": updated["ALERT_STATUS"],
                    "detect_count": updated["DETECT_COUNT"],
                }

            connection.commit()
            return result

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def resolve_alert(self, alert_key, reason):
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE WEBHOOK_METRICS_ALERT
                    SET
                        ALERT_STATUS = 'RESOLVED',
                        RESOLVED_AT = CURRENT_TIMESTAMP(3),
                        RESOLUTION_REASON = %s
                    WHERE ALERT_KEY = %s
                      AND ALERT_STATUS IN (
                          'OPEN',
                          'ACKNOWLEDGED'
                      )
                    """,
                    (reason, alert_key),
                )

                changed = cursor.rowcount == 1

            connection.commit()
            return changed

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def get_alert(self, alert_key):
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ID,
                        ALERT_KEY,
                        ALERT_TYPE,
                        ALERT_LEVEL,
                        ALERT_MESSAGE,
                        ALERT_STATUS,
                        DETECT_COUNT,
                        RESOLVED_AT,
                        RESOLUTION_REASON
                    FROM WEBHOOK_METRICS_ALERT
                    WHERE ALERT_KEY = %s
                    """,
                    (alert_key,),
                )

                return cursor.fetchone()

        finally:
            connection.close()
