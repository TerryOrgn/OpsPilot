
import pymysql

from db import get_connection
from uuid import uuid4
from db import get_connection

class WebhookNotificationOutboxRepository:

    def create_notification(
        self,
        event_id,
        alert_key,
        event_type,
        payload,
        channel="MOCK",
    ):
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must not be empty")

        if not isinstance(alert_key, str) or not alert_key.strip():
            raise ValueError("alert_key must not be empty")

        if event_type not in ("CREATED", "REOPENED", "RESOLVED"):
            raise ValueError(
                f"Unsupported event_type: {event_type!r}"
            )

        if not isinstance(payload, str) or not payload:
            raise ValueError("payload must not be empty")

        if not isinstance(channel, str) or not channel.strip():
            raise ValueError("channel must not be empty")

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        """
                        INSERT INTO WEBHOOK_NOTIFICATION_OUTBOX (
                            EVENT_ID,
                            ALERT_KEY,
                            EVENT_TYPE,
                            CHANNEL,
                            PAYLOAD
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            event_id,
                            alert_key,
                            event_type,
                            channel,
                            payload,
                        ),
                    )

                    notification_id = cursor.lastrowid

                    connection.commit()

                    return {
                        "notification_id": notification_id,
                        "event_id": event_id,
                        "event_type": "CREATED",
                    }

                except pymysql.err.IntegrityError as exc:
                    # 1062 = Duplicate entry
                    if exc.args[0] != 1062:
                        raise

                    connection.rollback()

                    cursor.execute(
                        """
                        SELECT ID
                        FROM WEBHOOK_NOTIFICATION_OUTBOX
                        WHERE EVENT_ID = %s
                        """,
                        (event_id,),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        raise RuntimeError(
                            "Duplicate event detected, "
                            "but existing row was not found"
                        )

                    # 支持 DictCursor 和普通 Cursor
                    notification_id = (
                        row["ID"]
                        if isinstance(row, dict)
                        else row[0]
                    )

                    return {
                        "notification_id": notification_id,
                        "event_id": event_id,
                        "event_type": "DUPLICATE",
                    }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()




    def claim_notification(
        self,
        notification_id,
        lease_seconds=300,
    ):
        """
        原子领取通知任务并生成 Lease。

        保留原有返回字段：
            notification_id
            event_type

        新增：
            claim_token
            lease_expires_at

        注意：
            本阶段只允许领取 PENDING 或到期 RETRY。
            不允许直接重新领取 SENDING。
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds <= 0
        ):
            raise ValueError(
                "lease_seconds must be a positive integer"
            )

        claim_token = uuid4().hex

        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = 'SENDING',
                        CLAIMED_AT = CURRENT_TIMESTAMP(6),
                        LEASE_EXPIRES_AT = DATE_ADD(
                            CURRENT_TIMESTAMP(6),
                            INTERVAL %s SECOND
                        ),
                        CLAIM_TOKEN = %s,
                        NEXT_RETRY_AT = NULL
                    WHERE ID = %s
                      AND (
                          STATUS = 'PENDING'
                          OR (
                              STATUS = 'RETRY'
                              AND NEXT_RETRY_AT IS NOT NULL
                              AND NEXT_RETRY_AT <=
                                  CURRENT_TIMESTAMP(6)
                          )
                      )
                    """,
                    (
                        lease_seconds,
                        claim_token,
                        notification_id,
                    ),
                )

                claimed = cursor.rowcount == 1

                if claimed:
                    cursor.execute(
                        """
                        SELECT LEASE_EXPIRES_AT
                        FROM WEBHOOK_NOTIFICATION_OUTBOX
                        WHERE ID = %s
                          AND CLAIM_TOKEN = %s
                        """,
                        (
                            notification_id,
                            claim_token,
                        ),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        raise RuntimeError(
                            "Claimed notification not found"
                        )

                    if isinstance(row, dict):
                        lease_expires_at = row[
                            "LEASE_EXPIRES_AT"
                        ]
                    else:
                        lease_expires_at = row[0]

                else:
                    lease_expires_at = None

            connection.commit()

            if claimed:
                return {
                    "notification_id": notification_id,
                    "event_type": "CLAIMED",
                    "claim_token": claim_token,
                    "lease_expires_at": lease_expires_at,
                }

            return {
                "notification_id": notification_id,
                "event_type": "NOT_CLAIMED",
                "claim_token": None,
                "lease_expires_at": None,
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()




    def mark_sent(self, notification_id):
        """
        Deprecated: 禁止无 Token 确认任务成功。

        请使用 mark_sent_with_token()。
        """
        raise RuntimeError(
            "Unsafe legacy API is disabled: "
            "use mark_sent_with_token()"
        )




    def mark_failed(
        self,
        notification_id,
        error_message,
        retry_delay_seconds=60,
    ):
        """
        Deprecated: 禁止无 Token 修改任务失败状态。

        请使用 mark_failed_with_token()。
        """
        raise RuntimeError(
            "Unsafe legacy API is disabled: "
            "use mark_failed_with_token()"
        )


    def get_due_notifications(self, limit=10):
        """
        查询可领取的通知任务。

        包含：
        1. PENDING
        2. 已到期的 RETRY

        只负责发现，不负责领取。
        """

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ID,
                        EVENT_ID,
                        STATUS,
                        RETRY_COUNT,
                        MAX_RETRIES,
                        NEXT_RETRY_AT,
                        CREATED_AT
                    FROM WEBHOOK_NOTIFICATION_OUTBOX
                    WHERE
                        STATUS = 'PENDING'
                        OR (
                            STATUS = 'RETRY'
                            AND NEXT_RETRY_AT IS NOT NULL
                            AND NEXT_RETRY_AT <= CURRENT_TIMESTAMP(6)
                        )
                    ORDER BY
                        CREATED_AT ASC,
                        ID ASC
                    LIMIT %s
                    """,
                    (limit,),
                )

                rows = cursor.fetchall()

                if not rows:
                    return []

                if isinstance(rows[0], dict):
                    return list(rows)

                columns = [
                    column[0]
                    for column in cursor.description
                ]

                return [
                    dict(zip(columns, row))
                    for row in rows
                ]

        finally:
            connection.close()


    def get_stale_sending_notifications(
        self,
        timeout_seconds=300,
        limit=100,
    ):
        """
        查询长时间处于 SENDING 状态的通知任务。

        Args:
            timeout_seconds: 超时阈值，默认 300 秒
            limit: 最大返回数量，范围 1~100

        Returns:
            list[dict]: 疑似超时的 SENDING 任务

        注意：
            只读查询，不改变任务状态。
        """

        # 1. 参数校验
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds must be a positive integer"
            )

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        # 2. 获取数据库连接
        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                # 3. 只查询超时的 SENDING 任务
                cursor.execute(
                    """
                    SELECT
                        ID,
                        EVENT_ID,
                        STATUS,
                        RETRY_COUNT,
                        UPDATED_AT
                    FROM WEBHOOK_NOTIFICATION_OUTBOX
                    WHERE STATUS = 'SENDING'
                      AND UPDATED_AT <= DATE_SUB(
                          CURRENT_TIMESTAMP(6),
                          INTERVAL %s SECOND
                      )
                    ORDER BY
                        UPDATED_AT ASC,
                        ID ASC
                    LIMIT %s
                    """,
                    (
                        timeout_seconds,
                        limit,
                    ),
                )

                rows = cursor.fetchall()

                if not rows:
                    return []

                # 4. 兼容 DictCursor 和普通 Cursor
                if isinstance(rows[0], dict):
                    return list(rows)

                columns = [
                    column[0]
                    for column in cursor.description
                ]

                return [
                    dict(zip(columns, row))
                    for row in rows
                ]

        finally:
            connection.close()


    def mark_sent_with_token(
        self,
        notification_id,
        claim_token,
    ):
        """
        只有持有有效 Lease Token 的 Worker
        才能确认任务发送成功。
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            not isinstance(claim_token, str)
            or not claim_token.strip()
        ):
            raise ValueError(
                "claim_token must be a non-empty string"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = 'SENT',
                        SENT_AT = CURRENT_TIMESTAMP(6),
                        LAST_ERROR = NULL,
                        NEXT_RETRY_AT = NULL,
                        CLAIM_TOKEN = NULL,
                        LEASE_EXPIRES_AT = NULL
                    WHERE ID = %s
                      AND STATUS = 'SENDING'
                      AND CLAIM_TOKEN = %s
                      AND LEASE_EXPIRES_AT >
                          CURRENT_TIMESTAMP(6)
                    """,
                    (
                        notification_id,
                        claim_token,
                    ),
                )

                updated = cursor.rowcount == 1

            connection.commit()

            return {
                "notification_id": notification_id,
                "event_type": (
                    "MARKED_SENT"
                    if updated
                    else "NOT_UPDATED"
                ),
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def mark_failed_with_token(
        self,
        notification_id,
        claim_token,
        error_message,
        retry_delay_seconds=60,
    ):
        """
        只有持有有效 Lease Token 的 Worker
        才能记录失败和安排重试。
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            not isinstance(claim_token, str)
            or not claim_token.strip()
        ):
            raise ValueError(
                "claim_token must be a non-empty string"
            )

        if (
            not isinstance(error_message, str)
            or not error_message.strip()
        ):
            raise ValueError(
                "error_message must be a non-empty string"
            )

        if (
            isinstance(retry_delay_seconds, bool)
            or not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN 'DEAD'
                            ELSE 'RETRY'
                        END,
                        NEXT_RETRY_AT = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN NULL
                            ELSE DATE_ADD(
                                CURRENT_TIMESTAMP(6),
                                INTERVAL %s SECOND
                            )
                        END,
                        LAST_ERROR = %s,
                        RETRY_COUNT = RETRY_COUNT + 1,
                        CLAIM_TOKEN = NULL,
                        LEASE_EXPIRES_AT = NULL
                    WHERE ID = %s
                      AND STATUS = 'SENDING'
                      AND CLAIM_TOKEN = %s
                      AND LEASE_EXPIRES_AT >
                          CURRENT_TIMESTAMP(6)
                    """,
                    (
                        retry_delay_seconds,
                        error_message[:1000],
                        notification_id,
                        claim_token,
                    ),
                )

                updated = cursor.rowcount == 1

                if updated:
                    cursor.execute(
                        """
                        SELECT STATUS, RETRY_COUNT
                        FROM WEBHOOK_NOTIFICATION_OUTBOX
                        WHERE ID = %s
                        """,
                        (notification_id,),
                    )

                    row = cursor.fetchone()

                    if isinstance(row, dict):
                        status = row["STATUS"]
                        retry_count = row["RETRY_COUNT"]
                    else:
                        status, retry_count = row

                else:
                    status = None
                    retry_count = None

            connection.commit()

            if not updated:
                event_type = "NOT_UPDATED"
            elif status == "DEAD":
                event_type = "MARKED_DEAD"
            else:
                event_type = "RETRY_SCHEDULED"

            return {
                "notification_id": notification_id,
                "event_type": event_type,
                "retry_count": retry_count,
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()


    def mark_sent_with_token(
        self,
        notification_id,
        claim_token,
    ):
        """
        只有持有有效 Lease Token 的 Worker
        才能确认任务发送成功。
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            not isinstance(claim_token, str)
            or not claim_token.strip()
        ):
            raise ValueError(
                "claim_token must be a non-empty string"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = 'SENT',
                        SENT_AT = CURRENT_TIMESTAMP(6),
                        LAST_ERROR = NULL,
                        NEXT_RETRY_AT = NULL,
                        CLAIM_TOKEN = NULL,
                        LEASE_EXPIRES_AT = NULL
                    WHERE ID = %s
                      AND STATUS = 'SENDING'
                      AND CLAIM_TOKEN = %s
                      AND LEASE_EXPIRES_AT >
                          CURRENT_TIMESTAMP(6)
                    """,
                    (
                        notification_id,
                        claim_token,
                    ),
                )

                updated = cursor.rowcount == 1

            connection.commit()

            return {
                "notification_id": notification_id,
                "event_type": (
                    "MARKED_SENT"
                    if updated
                    else "NOT_UPDATED"
                ),
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    def mark_failed_with_token(
        self,
        notification_id,
        claim_token,
        error_message,
        retry_delay_seconds=60,
    ):
        """
        只有持有有效 Lease Token 的 Worker
        才能记录失败和安排重试。
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            not isinstance(claim_token, str)
            or not claim_token.strip()
        ):
            raise ValueError(
                "claim_token must be a non-empty string"
            )

        if (
            not isinstance(error_message, str)
            or not error_message.strip()
        ):
            raise ValueError(
                "error_message must be a non-empty string"
            )

        if (
            isinstance(retry_delay_seconds, bool)
            or not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN 'DEAD'
                            ELSE 'RETRY'
                        END,
                        NEXT_RETRY_AT = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN NULL
                            ELSE DATE_ADD(
                                CURRENT_TIMESTAMP(6),
                                INTERVAL %s SECOND
                            )
                        END,
                        LAST_ERROR = %s,
                        RETRY_COUNT = RETRY_COUNT + 1,
                        CLAIM_TOKEN = NULL,
                        LEASE_EXPIRES_AT = NULL
                    WHERE ID = %s
                      AND STATUS = 'SENDING'
                      AND CLAIM_TOKEN = %s
                      AND LEASE_EXPIRES_AT >
                          CURRENT_TIMESTAMP(6)
                    """,
                    (
                        retry_delay_seconds,
                        error_message[:1000],
                        notification_id,
                        claim_token,
                    ),
                )

                updated = cursor.rowcount == 1

                if updated:
                    cursor.execute(
                        """
                        SELECT STATUS, RETRY_COUNT
                        FROM WEBHOOK_NOTIFICATION_OUTBOX
                        WHERE ID = %s
                        """,
                        (notification_id,),
                    )

                    row = cursor.fetchone()

                    if isinstance(row, dict):
                        status = row["STATUS"]
                        retry_count = row["RETRY_COUNT"]
                    else:
                        status, retry_count = row

                else:
                    status = None
                    retry_count = None

            connection.commit()

            if not updated:
                event_type = "NOT_UPDATED"
            elif status == "DEAD":
                event_type = "MARKED_DEAD"
            else:
                event_type = "RETRY_SCHEDULED"

            return {
                "notification_id": notification_id,
                "event_type": event_type,
                "retry_count": retry_count,
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()


    def get_expired_lease_notifications(self, limit=100):
        """
        只读查询 Lease 已过期的 SENDING 任务。

        不修改状态。
        不自动重新领取。
        不处理旧数据中 NULL Lease 的任务。
        """

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError(
                "limit must be an integer between 1 and 100"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ID,
                        EVENT_ID,
                        STATUS,
                        RETRY_COUNT,
                        MAX_RETRIES,
                        CLAIMED_AT,
                        LEASE_EXPIRES_AT,
                        CLAIM_TOKEN
                    FROM WEBHOOK_NOTIFICATION_OUTBOX
                    WHERE STATUS = 'SENDING'
                      AND LEASE_EXPIRES_AT IS NOT NULL
                      AND LEASE_EXPIRES_AT <=
                          CURRENT_TIMESTAMP(6)
                    ORDER BY
                        LEASE_EXPIRES_AT ASC,
                        ID ASC
                    LIMIT %s
                    """,
                    (limit,),
                )

                rows = cursor.fetchall()

                if rows and not isinstance(rows[0], dict):
                    columns = [
                        item[0]
                        for item in cursor.description
                    ]

                    rows = [
                        dict(zip(columns, row))
                        for row in rows
                    ]

                return list(rows)

        finally:
            connection.close()


    def recover_expired_lease(
        self,
        notification_id,
        expected_claim_token,
        retry_delay_seconds=60,
    ):
        """
        原子恢复 Lease 已过期的 SENDING 任务。

        expected_claim_token:
            必须是恢复扫描时观察到的 Token。

        返回：
            RECOVERED_RETRY
            RECOVERED_DEAD
            NOT_RECOVERED
        """

        if (
            isinstance(notification_id, bool)
            or not isinstance(notification_id, int)
            or notification_id <= 0
        ):
            raise ValueError(
                "notification_id must be a positive integer"
            )

        if (
            not isinstance(expected_claim_token, str)
            or not expected_claim_token.strip()
        ):
            raise ValueError(
                "expected_claim_token must be non-empty"
            )

        if (
            isinstance(retry_delay_seconds, bool)
            or not isinstance(retry_delay_seconds, int)
            or retry_delay_seconds < 0
        ):
            raise ValueError(
                "retry_delay_seconds must be non-negative"
            )

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                    SET
                        STATUS = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN 'DEAD'
                            ELSE 'RETRY'
                        END,
                        NEXT_RETRY_AT = CASE
                            WHEN RETRY_COUNT + 1 >= MAX_RETRIES
                                THEN NULL
                            ELSE DATE_ADD(
                                CURRENT_TIMESTAMP(6),
                                INTERVAL %s SECOND
                            )
                        END,
                        LAST_ERROR = 'LEASE_EXPIRED: outcome unknown',
                        RETRY_COUNT = RETRY_COUNT + 1,
                        CLAIM_TOKEN = NULL,
                        CLAIMED_AT = NULL,
                        LEASE_EXPIRES_AT = NULL
                    WHERE ID = %s
                      AND STATUS = 'SENDING'
                      AND CLAIM_TOKEN = %s
                      AND LEASE_EXPIRES_AT IS NOT NULL
                      AND LEASE_EXPIRES_AT <=
                          CURRENT_TIMESTAMP(6)
                    """,
                    (
                        retry_delay_seconds,
                        notification_id,
                        expected_claim_token,
                    ),
                )

                updated = cursor.rowcount == 1

                if updated:
                    cursor.execute(
                        """
                        SELECT STATUS, RETRY_COUNT
                        FROM WEBHOOK_NOTIFICATION_OUTBOX
                        WHERE ID = %s
                        """,
                        (notification_id,),
                    )

                    row = cursor.fetchone()

                    if row is None:
                        raise RuntimeError(
                            "Recovered notification not found"
                        )

                    if isinstance(row, dict):
                        status = row["STATUS"]
                        retry_count = row["RETRY_COUNT"]
                    else:
                        status, retry_count = row
                else:
                    status = None
                    retry_count = None

            connection.commit()

            if not updated:
                event_type = "NOT_RECOVERED"
            elif status == "DEAD":
                event_type = "RECOVERED_DEAD"
            else:
                event_type = "RECOVERED_RETRY"

            return {
                "notification_id": notification_id,
                "event_type": event_type,
                "retry_count": retry_count,
            }

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()
