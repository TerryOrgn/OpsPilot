
from db import get_connection


def get_pending_fallback_alerts(limit=10):
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit <= 0
    ):
        raise ValueError(
            "limit must be a positive integer"
        )

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ALERT_ID,
                    NOTIFICATION_TYPE,
                    OLD_STATUS,
                    NEW_STATUS,
                    STATUS,
                    CREATED_AT
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE STATUS = 'PENDING'
                ORDER BY CREATED_AT, ALERT_ID
                LIMIT %s
                """,
                (limit,)
            )

            rows = cursor.fetchall()
            columns = [
                item[0] for item in cursor.description
            ]

            return [
                row if isinstance(row, dict)
                else dict(zip(columns, row))
                for row in rows
            ]

    finally:
        conn.close()



from uuid import uuid4


def claim_pending_fallback_alerts(limit=10):
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit <= 0
    ):
        raise ValueError("limit must be a positive integer")

    conn = get_connection()

    try:
        # 显式开启事务，确保行锁持续到提交
        conn.begin()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ALERT_ID,
                    NOTIFICATION_TYPE,
                    OLD_STATUS,
                    NEW_STATUS
                FROM JOB_OUTBOX_FALLBACK_ALERT
                WHERE STATUS = 'PENDING'
                ORDER BY CREATED_AT, ALERT_ID
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,)
            )

            rows = cursor.fetchall()
            columns = [
                item[0] for item in cursor.description
            ]

            alerts = [
                row if isinstance(row, dict)
                else dict(zip(columns, row))
                for row in rows
            ]

            for alert in alerts:
                claim_token = str(uuid4())

                cursor.execute(
                    """
                    UPDATE JOB_OUTBOX_FALLBACK_ALERT
                    SET STATUS = 'PROCESSING',
                        CLAIM_TOKEN = %s,
                        CLAIMED_AT = CURRENT_TIMESTAMP(3),
                        RETRY_COUNT = RETRY_COUNT + 1
                    WHERE ALERT_ID = %s
                      AND STATUS = 'PENDING'
                    """,
                    (
                        claim_token,
                        alert["ALERT_ID"]
                    )
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Failed to claim alert "
                        f"{alert['ALERT_ID']}"
                    )

                alert["CLAIM_TOKEN"] = claim_token
                alert["STATUS"] = "PROCESSING"

        conn.commit()
        return alerts

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def confirm_fallback_alert_sent(alert_id, claim_token):
    if (
        not isinstance(alert_id, int)
        or isinstance(alert_id, bool)
        or alert_id <= 0
    ):
        raise ValueError("alert_id must be a positive integer")

    if not isinstance(claim_token, str) or not claim_token:
        raise ValueError("claim_token must be a non-empty string")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET STATUS = 'SENT',
                    CLAIM_TOKEN = NULL,
                    CLAIMED_AT = NULL
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
                """,
                (alert_id, claim_token)
            )

            updated = cursor.rowcount == 1

        conn.commit()
        return updated

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def confirm_fallback_alert_failed(alert_id, claim_token):
    if (
        not isinstance(alert_id, int)
        or isinstance(alert_id, bool)
        or alert_id <= 0
    ):
        raise ValueError("alert_id must be a positive integer")

    if not isinstance(claim_token, str) or not claim_token:
        raise ValueError("claim_token must be a non-empty string")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET STATUS        = CASE
                                        WHEN RETRY_COUNT >= 3
                                            THEN 'EXHAUSTED'
                                        ELSE 'FAILED'
                    END,
                    CLAIM_TOKEN   = NULL,
                    CLAIMED_AT    = NULL,
                    NEXT_RETRY_AT = CASE
                                        WHEN RETRY_COUNT = 1
                                            THEN DATE_ADD(
                                                CURRENT_TIMESTAMP(3),
                                                INTERVAL 60 SECOND
                            )
                                        WHEN RETRY_COUNT = 2
                                            THEN DATE_ADD(
                                                CURRENT_TIMESTAMP(3),
                                                INTERVAL 120 SECOND
                            )
                                        ELSE NULL
                        END
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
                """,
                (alert_id, claim_token)
            )

            updated = cursor.rowcount == 1

        conn.commit()
        return updated

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def requeue_due_failed_fallback_alerts():
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET STATUS = 'PENDING',
                    NEXT_RETRY_AT = NULL
                WHERE STATUS = 'FAILED'
                  AND RETRY_COUNT < 3
                  AND NEXT_RETRY_AT IS NOT NULL
                  AND NEXT_RETRY_AT <= CURRENT_TIMESTAMP(3)
                """
            )

            requeued_count = cursor.rowcount

        conn.commit()
        return requeued_count

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def recover_stale_fallback_alerts(
    timeout_seconds=300,
    max_attempts=3
):
    for name, value in [
        ("timeout_seconds", timeout_seconds),
        ("max_attempts", max_attempts),
    ]:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"{name} must be a positive integer"
            )

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET STATUS = CASE
                        WHEN RETRY_COUNT >= %s
                            THEN 'EXHAUSTED'
                        ELSE 'PENDING'
                    END,
                    CLAIM_TOKEN = NULL,
                    CLAIMED_AT = NULL,
                    NEXT_RETRY_AT = NULL
                WHERE STATUS = 'PROCESSING'
                  AND CLAIMED_AT IS NOT NULL
                  AND CLAIMED_AT <= DATE_SUB(
                      CURRENT_TIMESTAMP(3),
                      INTERVAL %s SECOND
                  )
                """,
                (max_attempts, timeout_seconds)
            )

            recovered_count = cursor.rowcount

        conn.commit()
        return recovered_count

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def confirm_fallback_alert_conflict(alert_id, claim_token):
    """
    HTTP 409:
    停止自动重试，将告警转为 EXHAUSTED。

    只有当前 Claim Token 的持有者可以更新。
    """
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE JOB_OUTBOX_FALLBACK_ALERT
                SET STATUS = 'EXHAUSTED',
                    CLAIM_TOKEN = NULL,
                    CLAIMED_AT = NULL,
                    NEXT_RETRY_AT = NULL,
                    UPDATED_AT = CURRENT_TIMESTAMP(3)
                WHERE ALERT_ID = %s
                  AND STATUS = 'PROCESSING'
                  AND CLAIM_TOKEN = %s
            """, (alert_id, claim_token))

            updated = cursor.rowcount

        conn.commit()
        return updated == 1

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
