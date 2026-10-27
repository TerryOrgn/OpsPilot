
from db import get_connection
from uuid import uuid4


def get_pending_outbox_events(limit=10):
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    EVENT_ID,
                    NOTIFICATION_TYPE,
                    EVENT_TYPE,
                    STATUS,
                    CREATED_AT
                FROM JOB_MONITOR_EVENT_OUTBOX
                WHERE STATUS = 'PENDING'
                ORDER BY CREATED_AT, EVENT_ID
                LIMIT %s
                """,
                (limit,)
            )

            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description]

            return [
                row if isinstance(row, dict)
                else dict(zip(columns, row))
                for row in rows
            ]

    finally:
        conn.close()



def claim_pending_outbox_events(limit=10, notification_type=None):
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            # 在事务内锁定尚未被领取的事件

            if notification_type is None:
                cursor.execute(
                    """
                    SELECT
                        EVENT_ID,
                        NOTIFICATION_TYPE,
                        EVENT_TYPE
                    FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE STATUS = 'PENDING'
                    ORDER BY CREATED_AT, EVENT_ID
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (limit,)
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        EVENT_ID,
                        NOTIFICATION_TYPE,
                        EVENT_TYPE
                    FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE STATUS = 'PENDING'
                      AND NOTIFICATION_TYPE = %s
                    ORDER BY CREATED_AT, EVENT_ID
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (notification_type, limit)
                )


            rows = cursor.fetchall()
            columns = [item[0] for item in cursor.description]

            events = [
                row if isinstance(row, dict)
                else dict(zip(columns, row))
                for row in rows
            ]

            # 将领取到的事件标记为 PROCESSING
            for event in events:
                claim_token = str(uuid4())

                cursor.execute(
                    """
                    UPDATE JOB_MONITOR_EVENT_OUTBOX
                    SET STATUS      = 'PROCESSING',
                        CLAIMED_AT  = CURRENT_TIMESTAMP(3),
                        CLAIM_TOKEN = %s,
                        RETRY_COUNT = RETRY_COUNT + 1
                    WHERE EVENT_ID = %s
                      AND STATUS = 'PENDING'
                    """,
                    (claim_token, event["EVENT_ID"])
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Failed to claim EVENT_ID={event['EVENT_ID']}"
                    )

                # 将本次领取令牌返回给 Dispatcher
                event["CLAIM_TOKEN"] = claim_token

            conn.commit()
            return events

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def confirm_outbox_sent(event_id, claim_token):
    if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0:
        raise ValueError("event_id must be a positive integer")

    if not isinstance(claim_token, str) or not claim_token:
        raise ValueError("claim_token must be a non-empty string")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET
                    STATUS = 'SENT',
                    CLAIMED_AT = NULL,
                    CLAIM_TOKEN = NULL
                WHERE EVENT_ID = %s
                  AND CLAIM_TOKEN = %s
                  AND STATUS = 'PROCESSING'
                """,
                (event_id, claim_token)
            )

            updated = cursor.rowcount

        conn.commit()
        return updated == 1

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()




def recover_stale_outbox_events(
    timeout_seconds=300,
    max_attempts=3
):
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise ValueError(
            "timeout_seconds must be a positive integer"
        )

    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts <= 0
    ):
        raise ValueError(
            "max_attempts must be a positive integer"
        )

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET
                    
                    STATUS = CASE
                        WHEN RETRY_COUNT < %s THEN 'PENDING'
                        ELSE 'EXHAUSTED'
                    END,
                    CLAIMED_AT = NULL,
                    CLAIM_TOKEN = NULL,
                    NEXT_RETRY_AT = NULL
                WHERE STATUS = 'PROCESSING'
                  AND CLAIMED_AT IS NOT NULL
                  AND CLAIMED_AT <
                      CURRENT_TIMESTAMP(3)
                      - INTERVAL %s SECOND
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



def confirm_outbox_failed(event_id, claim_token):
    if (
        not isinstance(event_id, int)
        or isinstance(event_id, bool)
        or event_id <= 0
    ):
        raise ValueError("event_id must be a positive integer")

    if not isinstance(claim_token, str) or not claim_token:
        raise ValueError("claim_token must be a non-empty string")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                UPDATE JOB_MONITOR_EVENT_OUTBOX
                SET STATUS = CASE
                        WHEN RETRY_COUNT >= 3 THEN 'EXHAUSTED'
                        ELSE 'FAILED'
                    END,
                    CLAIMED_AT    = NULL,
                    CLAIM_TOKEN   = NULL,
                    NEXT_RETRY_AT = CASE
                                        WHEN RETRY_COUNT = 1 THEN
                                            CURRENT_TIMESTAMP(3) + INTERVAL 60 SECOND
                    WHEN RETRY_COUNT = 2 THEN
                    CURRENT_TIMESTAMP (3) + INTERVAL 120 SECOND
                    ELSE NULL
                END
                WHERE EVENT_ID =
                %s
                AND
                CLAIM_TOKEN
                =
                %s
                AND
                STATUS
                =
                'PROCESSING'
                """,
                (event_id, claim_token)
            )

            updated = cursor.rowcount

        conn.commit()
        return updated == 1

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def requeue_due_failed_outbox_events(
    notification_type=None,
    max_attempts=3
):
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < 1
    ):
        raise ValueError("max_attempts must be a positive integer")

    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            if notification_type is None:
                cursor.execute(
                    """
                    UPDATE JOB_MONITOR_EVENT_OUTBOX
                    SET
                        STATUS = 'PENDING',
                        NEXT_RETRY_AT = NULL
                    WHERE STATUS = 'FAILED'
                      AND NEXT_RETRY_AT IS NOT NULL
                      AND NEXT_RETRY_AT <= CURRENT_TIMESTAMP(3)
                      AND RETRY_COUNT < %s
                    """,
                    (max_attempts,)
                )
            else:
                cursor.execute(
                    """
                    UPDATE JOB_MONITOR_EVENT_OUTBOX
                    SET
                        STATUS = 'PENDING',
                        NEXT_RETRY_AT = NULL
                    WHERE STATUS = 'FAILED'
                      AND NOTIFICATION_TYPE = %s
                      AND NEXT_RETRY_AT IS NOT NULL
                      AND NEXT_RETRY_AT <= CURRENT_TIMESTAMP(3)
                      AND RETRY_COUNT < %s
                    """,
                    (notification_type, max_attempts)
                )

            requeued_count = cursor.rowcount

        conn.commit()
        return requeued_count

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()



def get_exhausted_outbox_count(notification_type=None):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            if notification_type is None:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE STATUS = 'EXHAUSTED'
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM JOB_MONITOR_EVENT_OUTBOX
                    WHERE STATUS = 'EXHAUSTED'
                      AND NOTIFICATION_TYPE = %s
                    """,
                    (notification_type,)
                )

            row = cursor.fetchone()

            if isinstance(row, dict):
                return int(next(iter(row.values())))

            return int(row[0])

    finally:
        conn.close()


def evaluate_outbox_exhausted_status(exhausted_count):
    if (
        not isinstance(exhausted_count, int)
        or isinstance(exhausted_count, bool)
        or exhausted_count < 0
    ):
        raise ValueError(
            "exhausted_count must be a non-negative integer"
        )

    if exhausted_count > 0:
        return "ACTION_REQUIRED"

    return "NORMAL"

