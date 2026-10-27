
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

prefix = f"TEST-92-57-I-{uuid4().hex}"


def create_task(name):
    result = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-I:{name}",
        event_type="CREATED",
        payload=f"Worker test: {name}",
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
                    NEXT_RETRY_AT,
                    SENT_AT,
                    LAST_ERROR
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if isinstance(row, dict):
                return row

            columns = [
                column[0]
                for column in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


success_id = create_task("MOCK-SUCCESS")
failure_id = create_task("MOCK-FAIL")


class TestScopedRepository:
    """
    测试隔离适配器。

    只限制任务发现范围；
    其他操作全部委托给真实 Repository。
    """

    def __init__(self, actual_repository, allowed_ids):
        self.actual_repository = actual_repository
        self.allowed_ids = set(allowed_ids)

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
        assert notification_id in self.allowed_ids

        return self.actual_repository.claim_notification(
            notification_id
        )

    def mark_sent(self, notification_id):
        assert notification_id in self.allowed_ids

        return self.actual_repository.mark_sent(
            notification_id
        )

    def mark_failed(self, notification_id, error_message):
        assert notification_id in self.allowed_ids

        return self.actual_repository.mark_failed(
            notification_id,
            error_message,
        )


scoped_repo = TestScopedRepository(
    repo,
    [success_id, failure_id],
)

worker = WebhookNotificationOutboxWorker(
    repository=scoped_repo,
    sender=MockNotificationSender(),
)


# 1. 初始状态
assert get_row(success_id)["STATUS"] == "PENDING"
assert get_row(failure_id)["STATUS"] == "PENDING"

print("[TEST] INITIAL_PENDING= True")


# 2. 执行一轮
stats = worker.run_once(limit=10)

print("[INFO] WORKER_STATS=", stats)


# 3. 发现两条任务
assert stats["discovered"] == 2
print("[TEST] DISCOVERED_TWO= True")


# 4. 成功领取两条
assert stats["claimed"] == 2
print("[TEST] CLAIMED_TWO= True")


# 5. 成功发送一条
assert stats["sent"] == 1
assert get_row(success_id)["STATUS"] == "SENT"
assert get_row(success_id)["SENT_AT"] is not None

print("[TEST] SUCCESS_MARKED_SENT= True")


# 6. 失败一条并安排重试
failure_row = get_row(failure_id)

assert stats["retry"] == 1
assert failure_row["STATUS"] == "RETRY"
assert failure_row["RETRY_COUNT"] == 1
assert failure_row["NEXT_RETRY_AT"] is not None
assert "Simulated" in failure_row["LAST_ERROR"]

print("[TEST] FAILURE_SCHEDULED_RETRY= True")


# 7. 未达到 DEAD
assert stats["dead"] == 0
print("[TEST] NO_DEAD= True")


# 8. 没有跳过任务
assert stats["skipped"] == 0
print("[TEST] NO_SKIPPED= True")


# 9. 立即再次运行
second_stats = worker.run_once(limit=10)

assert second_stats["discovered"] == 0
assert second_stats["claimed"] == 0
assert second_stats["sent"] == 0

print("[TEST] SECOND_RUN_NO_DUPLICATE= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox worker"
)
