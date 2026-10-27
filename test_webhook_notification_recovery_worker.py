
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)
from webhook_notification_recovery_worker import (
    WebhookNotificationRecoveryWorker,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-T-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-T:{name}",
        event_type="CREATED",
        payload=f"Recovery Worker test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id, claimed["claim_token"]


def execute_sql(sql, params):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_row(notification_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    LEASE_EXPIRES_AT,
                    NEXT_RETRY_AT
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if isinstance(row, dict):
                return row

            columns = [
                item[0]
                for item in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


# 创建测试任务
retry_id, retry_token = create_and_claim("RETRY")
dead_id, dead_token = create_and_claim("DEAD")
valid_id, valid_token = create_and_claim("VALID")


# 模拟 RETRY 任务租约过期
execute_sql(
    """
    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
    SET LEASE_EXPIRES_AT = DATE_SUB(
        CURRENT_TIMESTAMP(6),
        INTERVAL 10 SECOND
    )
    WHERE ID = %s
    """,
    (retry_id,),
)


# 模拟 DEAD 任务租约过期
execute_sql(
    """
    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
    SET
        RETRY_COUNT = MAX_RETRIES - 1,
        LEASE_EXPIRES_AT = DATE_SUB(
            CURRENT_TIMESTAMP(6),
            INTERVAL 10 SECOND
        )
    WHERE ID = %s
    """,
    (dead_id,),
)


class ScopedRecoveryRepository:
    """
    限定扫描范围，真实恢复仍使用 MySQL Repository。
    """

    def __init__(self, actual, task_ids):
        self.actual = actual
        self.task_ids = set(task_ids)

    def get_expired_lease_notifications(self, limit=100):
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        ID,
                        CLAIM_TOKEN,
                        STATUS,
                        LEASE_EXPIRES_AT
                    FROM WEBHOOK_NOTIFICATION_OUTBOX
                    WHERE ID IN (%s, %s, %s)
                      AND STATUS = 'SENDING'
                      AND LEASE_EXPIRES_AT IS NOT NULL
                      AND LEASE_EXPIRES_AT <=
                          CURRENT_TIMESTAMP(6)
                    ORDER BY ID
                    LIMIT %s
                    """,
                    (
                        retry_id,
                        dead_id,
                        valid_id,
                        limit,
                    ),
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
        assert notification_id in self.task_ids

        return self.actual.recover_expired_lease(
            notification_id,
            expected_claim_token,
            retry_delay_seconds=retry_delay_seconds,
        )


scoped_repo = ScopedRecoveryRepository(
    repo,
    [retry_id, dead_id, valid_id],
)

worker = WebhookNotificationRecoveryWorker(
    repository=scoped_repo
)


# 1. 执行恢复
stats = worker.run_once(
    limit=10,
    retry_delay_seconds=60,
)

assert stats["discovered"] == 2

print("[TEST] EXPIRED_TASKS_DISCOVERED= True")


# 2. RETRY 分支
retry_row = get_row(retry_id)

assert stats["recovered_retry"] == 1
assert retry_row["STATUS"] == "RETRY"
assert retry_row["RETRY_COUNT"] == 1

print("[TEST] EXPIRED_TASK_RECOVERED_TO_RETRY= True")


# 3. DEAD 分支
dead_row = get_row(dead_id)

assert stats["recovered_dead"] == 1
assert dead_row["STATUS"] == "DEAD"
assert dead_row["RETRY_COUNT"] == 3

print("[TEST] MAX_RETRIES_RECOVERED_TO_DEAD= True")


# 4. 旧 Token 清除
assert retry_row["CLAIM_TOKEN"] is None
assert dead_row["CLAIM_TOKEN"] is None

assert retry_row["LEASE_EXPIRES_AT"] is None
assert dead_row["LEASE_EXPIRES_AT"] is None

print("[TEST] OLD_LEASE_CLEARED= True")


# 5. 有效 Lease 不受影响
valid_row = get_row(valid_id)

assert valid_row["STATUS"] == "SENDING"
assert valid_row["CLAIM_TOKEN"] == valid_token

print("[TEST] VALID_LEASE_UNCHANGED= True")


# 6. 正常执行无错误
assert stats["errors"] == 0
assert stats["skipped"] == 0

print("[TEST] NO_RECOVERY_ERRORS= True")


# 7. 第二轮不会重复恢复
second_stats = worker.run_once(limit=10)

assert second_stats["discovered"] == 0
assert second_stats["recovered_retry"] == 0
assert second_stats["recovered_dead"] == 0

print("[TEST] SECOND_RUN_NO_DUPLICATE= True")


# 8. 非法 limit 被拒绝
for invalid in (0, -1, 101, None, True):
    try:
        worker.run_once(limit=invalid)
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_LIMIT_REJECTED= True")


print("[INFO] RETRY_ID=", retry_id)
print("[INFO] DEAD_ID=", dead_id)
print("[INFO] VALID_ID=", valid_id)
print("[INFO] RECOVERY_STATS=", stats)

print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery worker"
)
