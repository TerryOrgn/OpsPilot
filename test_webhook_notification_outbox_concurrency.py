
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from threading import Barrier
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


THREAD_COUNT = 10

EVENT_ID = f"TEST-92-57-C-{uuid4().hex}"
ALERT_KEY = "TEST-92-57-C:WEBHOOK_ERROR_RATE"

# 让 10 个线程尽量同时开始写入
barrier = Barrier(THREAD_COUNT)


def write_notification(worker_id):
    repository = WebhookNotificationOutboxRepository()

    barrier.wait(timeout=15)

    result = repository.create_notification(
        event_id=EVENT_ID,
        alert_key=ALERT_KEY,
        event_type="CREATED",
        payload="Concurrent webhook alert test",
        channel="MOCK",
    )

    return {
        "worker_id": worker_id,
        "notification_id": result["notification_id"],
        "event_type": result["event_type"],
    }


def query_database():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ID, STATUS
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (EVENT_ID,),
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
        connection.close()


def main():
    results = []

    # 1. 并发写入
    with ThreadPoolExecutor(
        max_workers=THREAD_COUNT
    ) as executor:

        futures = [
            executor.submit(write_notification, i)
            for i in range(THREAD_COUNT)
        ]

        for future in as_completed(futures):
            results.append(future.result())

    assert len(results) == THREAD_COUNT

    print("[TEST] ALL_THREADS_COMPLETED= True")

    # 2. 检查 CREATED / DUPLICATE 数量
    created = [
        r for r in results
        if r["event_type"] == "CREATED"
    ]

    duplicates = [
        r for r in results
        if r["event_type"] == "DUPLICATE"
    ]

    print(f"[INFO] CREATED_COUNT={len(created)}")
    print(f"[INFO] DUPLICATE_COUNT={len(duplicates)}")

    assert len(created) == 1
    assert len(duplicates) == THREAD_COUNT - 1

    print("[TEST] ONE_CREATED_NINE_DUPLICATE= True")

    # 3. 检查所有线程返回同一个数据库 ID
    notification_ids = {
        r["notification_id"]
        for r in results
    }

    assert len(notification_ids) == 1

    notification_id = notification_ids.pop()

    print("[TEST] SAME_NOTIFICATION_ID= True")

    # 4. 查询 MySQL
    rows = query_database()

    assert len(rows) == 1

    print("[TEST] DATABASE_ONLY_ONE_ROW= True")

    # 5. 检查数据库 ID 与状态
    row = rows[0]

    assert row["ID"] == notification_id
    assert row["STATUS"] == "PENDING"

    print("[TEST] DATABASE_STATE_CORRECT= True")

    # 6. 输出每个线程结果
    for result in sorted(
        results,
        key=lambda x: x["worker_id"]
    ):
        print(
            f"[WORKER-{result['worker_id']}] "
            f"event={result['event_type']} "
            f"id={result['notification_id']}"
        )

    print(
        "[TEST] ALL PASS: "
        "Webhook notification outbox concurrency"
    )


if __name__ == "__main__":
    main()
