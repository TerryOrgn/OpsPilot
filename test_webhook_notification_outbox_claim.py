
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


THREAD_COUNT = 10

repository = WebhookNotificationOutboxRepository()

event_id = f"TEST-92-57-D-{uuid4().hex}"

created = repository.create_notification(
    event_id=event_id,
    alert_key="TEST-92-57-D:WEBHOOK_ERROR_RATE",
    event_type="CREATED",
    payload="Test atomic notification claim",
)

notification_id = created["notification_id"]

assert created["event_type"] == "CREATED"

print("[TEST] NOTIFICATION_CREATED= True")


def get_status():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise AssertionError("Notification not found")

            return (
                row["STATUS"]
                if isinstance(row, dict)
                else row[0]
            )

    finally:
        connection.close()


# 1. 创建后应为 PENDING
assert get_status() == "PENDING"

print("[TEST] INITIAL_PENDING= True")


# 2. 10 个 Worker 并发领取
barrier = Barrier(THREAD_COUNT)


def worker(worker_id):
    barrier.wait(timeout=15)

    result = (
        WebhookNotificationOutboxRepository()
        .claim_notification(notification_id)
    )

    return worker_id, result["event_type"]


with ThreadPoolExecutor(
    max_workers=THREAD_COUNT
) as executor:

    futures = [
        executor.submit(worker, i)
        for i in range(THREAD_COUNT)
    ]

    results = [
        future.result()
        for future in futures
    ]


assert len(results) == THREAD_COUNT

print("[TEST] ALL_WORKERS_COMPLETED= True")


# 3. 仅一个 Worker 成功领取
claimed = [
    result
    for result in results
    if result[1] == "CLAIMED"
]

not_claimed = [
    result
    for result in results
    if result[1] == "NOT_CLAIMED"
]

assert len(claimed) == 1
assert len(not_claimed) == THREAD_COUNT - 1

print("[TEST] SINGLE_WORKER_CLAIMED= True")


# 4. 最终数据库状态
assert get_status() == "SENDING"

print("[TEST] FINAL_STATUS_SENDING= True")


# 5. 再次领取必须失败
again = repository.claim_notification(
    notification_id
)

assert again["event_type"] == "NOT_CLAIMED"

print("[TEST] REPEATED_CLAIM_REJECTED= True")


# 6. 非法 ID 检查
for invalid_id in (0, -1, None, "123", True):
    try:
        repository.claim_notification(invalid_id)

    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError for {invalid_id!r}"
    )

print("[TEST] INVALID_ID_REJECTED= True")


# 7. 输出 Worker 结果
for worker_id, event_type in sorted(results):
    print(
        f"[WORKER-{worker_id}] "
        f"event={event_type}"
    )


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox claim"
)
