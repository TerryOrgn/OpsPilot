
import threading
import time
from uuid import uuid4

from db import get_connection

from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)
from webhook_notification_recovery_worker import (
    WebhookNotificationRecoveryWorker,
)
from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)

from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)






repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-W-{uuid4().hex}"


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
                    ID,
                    STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN,
                    CLAIMED_AT,
                    LEASE_EXPIRES_AT,
                    NEXT_RETRY_AT
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise AssertionError(
                    f"Notification not found: {notification_id}"
                )

            if isinstance(row, dict):
                return row

            columns = [
                item[0]
                for item in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-W:{name}",
        event_type="CREATED",
        payload=f"Integration test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id


# --------------------------------------------------
# 1. 创建三个独立测试任务
# --------------------------------------------------

retry_id = create_and_claim("RETRY")
dead_id = create_and_claim("DEAD")
valid_id = create_and_claim("VALID")

test_ids = (retry_id, dead_id, valid_id)


# 模拟两个任务的 Lease 过期
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


# --------------------------------------------------
# 2. 限定测试范围的 Repository
# --------------------------------------------------


class ScopedRecoveryRepository:

    def __init__(self, actual_repository, allowed_ids):
        self.actual = actual_repository

        ids = tuple(sorted(set(allowed_ids)))

        if not ids:
            raise ValueError(
                "Scoped repository requires allowed IDs"
            )

        if any(
            type(notification_id) is not int
            or notification_id <= 0
            for notification_id in ids
        ):
            raise ValueError(
                "Allowed IDs must be positive integers"
            )

        self.allowed_ids = frozenset(ids)
        self.scan_count = 0
        self.recovery_calls = []

    def get_expired_lease_notifications(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid scan limit")

        self.scan_count += 1

        ids = tuple(sorted(self.allowed_ids))
        placeholders = ", ".join(["%s"] * len(ids))

        sql = f"""
            SELECT
                ID,
                CLAIM_TOKEN,
                STATUS,
                LEASE_EXPIRES_AT
            FROM WEBHOOK_NOTIFICATION_OUTBOX
            WHERE ID IN ({placeholders})
              AND STATUS = 'SENDING'
              AND LEASE_EXPIRES_AT IS NOT NULL
              AND LEASE_EXPIRES_AT <= CURRENT_TIMESTAMP(6)
            ORDER BY ID
            LIMIT %s
        """

        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (*ids, limit),
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
        if notification_id not in self.allowed_ids:
            raise PermissionError(
                f"Recovery blocked for ID={notification_id}"
            )

        self.recovery_calls.append(notification_id)

        return self.actual.recover_expired_lease(
            notification_id,
            expected_claim_token,
            retry_delay_seconds=retry_delay_seconds,
        )




scoped_repo = ScopedRecoveryRepository(
    repo,
    test_ids,
)

# 验证白名单与本次测试任务一致
assert scoped_repo.allowed_ids == frozenset(test_ids)

print("[TEST] SCOPED_IDS_MATCH= True")


# 验证越权恢复被拒绝
# 使用非法 ID，不触发真实数据库恢复
try:
    scoped_repo.recover_expired_lease(
        notification_id=-1,
        expected_claim_token="invalid-token",
    )
except PermissionError:
    pass
else:
    raise AssertionError(
        "Out-of-scope recovery must be rejected"
    )

assert scoped_repo.recovery_calls == []

print("[TEST] OUT_OF_SCOPE_RECOVERY_BLOCKED= True")

real_worker = WebhookNotificationRecoveryWorker(
    repository=scoped_repo
)


# --------------------------------------------------
# 3. 创建真实 Recovery Scheduler
# --------------------------------------------------

# --------------------------------------------------
# 3. 创建 Guard + Recovery Scheduler
# --------------------------------------------------

guard = WebhookNotificationRecoveryGuard(
    repository=scoped_repo,
    worker=real_worker,
    enabled=True,
    dry_run=False,
    max_batch_size=10,
    retry_delay_seconds=60,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard,
    interval_seconds=0.2,
    limit=10,
    retry_delay_seconds=60,
)

# --------------------------------------------------
# 4. 自动调度集成测试
# --------------------------------------------------

try:
    scheduler.start()

    # 等待 APScheduler 自动触发至少一轮。
    # 使用有上限的轮询，不依赖固定次数的 sleep。
    deadline = time.monotonic() + 5

    while time.monotonic() < deadline:
        if (
            get_row(retry_id)["STATUS"] == "RETRY"
            and get_row(dead_id)["STATUS"] == "DEAD"
        ):
            break

        time.sleep(0.05)

    assert get_row(retry_id)["STATUS"] == "RETRY"
    assert get_row(dead_id)["STATUS"] == "DEAD"

finally:
    scheduler.stop()


print("[TEST] REAL_SCHEDULER_TRIGGERED= True")


# --------------------------------------------------
# 5. 验证 RETRY 结果
# --------------------------------------------------

retry_row = get_row(retry_id)

assert retry_row["RETRY_COUNT"] == 1
assert retry_row["NEXT_RETRY_AT"] is not None

print("[TEST] REAL_MYSQL_RETRY_RECOVERED= True")


# --------------------------------------------------
# 6. 验证 DEAD 结果
# --------------------------------------------------

dead_row = get_row(dead_id)

assert dead_row["STATUS"] == "DEAD"
assert dead_row["NEXT_RETRY_AT"] is None

print("[TEST] REAL_MYSQL_DEAD_RECOVERED= True")


# --------------------------------------------------
# 7. 验证旧 Lease 已清除
# --------------------------------------------------

for notification_id in (retry_id, dead_id):
    row = get_row(notification_id)

    assert row["CLAIM_TOKEN"] is None
    assert row["CLAIMED_AT"] is None
    assert row["LEASE_EXPIRES_AT"] is None

print("[TEST] REAL_MYSQL_LEASE_CLEARED= True")


# --------------------------------------------------
# 8. 有效 Lease 保持不变
# --------------------------------------------------

valid_row = get_row(valid_id)

assert valid_row["STATUS"] == "SENDING"
assert valid_row["CLAIM_TOKEN"] is not None
assert valid_row["LEASE_EXPIRES_AT"] is not None

print("[TEST] VALID_LEASE_UNCHANGED= True")


# --------------------------------------------------
# 9. 受限范围保护
# --------------------------------------------------

assert set(scoped_repo.recovery_calls).issubset(
    set(test_ids)
)

assert set(scoped_repo.recovery_calls) == {
    retry_id,
    dead_id,
}

print("[TEST] ONLY_SCOPED_TASKS_RECOVERED= True")


# --------------------------------------------------
# 10. 验证调度统计
# --------------------------------------------------

stats = scheduler.get_stats()

assert scoped_repo.scan_count >= 1
assert stats["success_count"] >= 1
assert stats["executed_count"] >= 1
assert stats["failure_count"] == 0
assert stats["disabled_count"] == 0
assert stats["dry_run_count"] == 0

print("[TEST] INTEGRATION_SCHEDULER_STATS= True")

# --------------------------------------------------
# 11. 不重复恢复
# --------------------------------------------------

assert get_row(retry_id)["RETRY_COUNT"] == 1

print("[TEST] NO_DUPLICATE_RECOVERY= True")


print("[INFO] RETRY_ID=", retry_id)
print("[INFO] DEAD_ID=", dead_id)
print("[INFO] VALID_ID=", valid_id)
print("[INFO] SCAN_COUNT=", scoped_repo.scan_count)
print("[INFO] RECOVERY_CALLS=", scoped_repo.recovery_calls)
print("[INFO] SCHEDULER_STATS=", stats)

print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery scheduler integration"
)
