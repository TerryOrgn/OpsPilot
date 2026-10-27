
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)
from webhook_notification_outbox_worker import (
    WebhookNotificationOutboxWorker,
    MockNotificationSender,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-O-{uuid4().hex}"


def create_task(name):
    result = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-O:{name}",
        event_type="CREATED",
        payload=f"Worker Lease test: {name}",
    )

    return result["notification_id"]


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
                    SENT_AT
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


success_id = create_task("MOCK-SUCCESS")
failure_id = create_task("MOCK-FAIL")


class ScopedRepository:
    """
    限定测试任务范围。

    真实领取和状态更新仍委托给 MySQL Repository。
    """

    def __init__(self, actual_repository, task_ids):
        self.actual = actual_repository
        self.task_ids = set(task_ids)

    def get_due_notifications(self, limit=10):
        connection = get_connection()

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ID, EVENT_ID, STATUS
                    FROM WEBHOOK_NOTIFICATION_OUTBOX
                    WHERE ID IN (%s, %s)
                      AND (
                          STATUS = 'PENDING'
                          OR (
                              STATUS = 'RETRY'
                              AND NEXT_RETRY_AT IS NOT NULL
                              AND NEXT_RETRY_AT <=
                                  CURRENT_TIMESTAMP(6)
                          )
                      )
                    ORDER BY ID
                    LIMIT %s
                    """,
                    (
                        success_id,
                        failure_id,
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

    def claim_notification(self, notification_id):
        assert notification_id in self.task_ids

        return self.actual.claim_notification(
            notification_id
        )

    def mark_sent_with_token(
        self,
        notification_id,
        claim_token,
    ):
        assert notification_id in self.task_ids

        return self.actual.mark_sent_with_token(
            notification_id,
            claim_token,
        )

    def mark_failed_with_token(
        self,
        notification_id,
        claim_token,
        error_message,
    ):
        assert notification_id in self.task_ids

        return self.actual.mark_failed_with_token(
            notification_id,
            claim_token,
            error_message,
        )


scoped_repo = ScopedRepository(
    repo,
    [success_id, failure_id],
)

worker = WebhookNotificationOutboxWorker(
    repository=scoped_repo,
    sender=MockNotificationSender(),
)


# 1. 执行 Worker
stats = worker.run_once(limit=10)

assert stats["discovered"] == 2
assert stats["claimed"] == 2

print("[TEST] BOTH_TASKS_CLAIMED= True")


# 2. 成功任务进入 SENT
success_row = get_row(success_id)

assert stats["sent"] == 1
assert success_row["STATUS"] == "SENT"
assert success_row["SENT_AT"] is not None

print("[TEST] SUCCESS_WITH_TOKEN= True")


# 3. 失败任务进入 RETRY
failure_row = get_row(failure_id)

assert stats["retry"] == 1
assert failure_row["STATUS"] == "RETRY"
assert failure_row["RETRY_COUNT"] == 1

print("[TEST] FAILURE_WITH_TOKEN= True")


# 4. 成功后清除 Token
assert success_row["CLAIM_TOKEN"] is None
assert success_row["LEASE_EXPIRES_AT"] is None

print("[TEST] SENT_LEASE_CLEARED= True")


# 5. 失败后清除 Token
assert failure_row["CLAIM_TOKEN"] is None
assert failure_row["LEASE_EXPIRES_AT"] is None

print("[TEST] RETRY_LEASE_CLEARED= True")


# 6. 正常执行没有所有权拒绝
assert stats["ownership_rejected"] == 0

print("[TEST] NO_OWNERSHIP_REJECTION= True")


# 7. 立即再次运行不会重复处理
second_stats = worker.run_once(limit=10)

assert second_stats["discovered"] == 0
assert second_stats["claimed"] == 0

print("[TEST] SECOND_RUN_NO_DUPLICATE= True")


print("[INFO] SUCCESS_ID=", success_id)
print("[INFO] FAILURE_ID=", failure_id)
print("[INFO] WORKER_STATS=", stats)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox worker lease"
)
