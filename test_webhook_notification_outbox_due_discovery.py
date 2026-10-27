
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()

prefix = f"TEST-92-57-H-{uuid4().hex}"


def create_task(name):
    result = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-H:{name}",
        event_type="CREATED",
        payload=f"Test due discovery: {name}",
    )
    return result["notification_id"]


def set_task_state(notification_id, status, retry_seconds=None):
    """
    仅用于构造测试数据。
    不属于生产业务接口。
    """
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                SET
                    STATUS = %s,
                    NEXT_RETRY_AT = CASE
                        WHEN %s IS NULL THEN NULL
                        ELSE DATE_ADD(
                            CURRENT_TIMESTAMP(6),
                            INTERVAL %s SECOND
                        )
                    END
                WHERE ID = %s
                """,
                (
                    status,
                    retry_seconds,
                    retry_seconds,
                    notification_id,
                ),
            )

            assert cursor.rowcount == 1

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def discover_test_ids(limit=100):
    rows = repo.get_due_notifications(limit=limit)

    return [
        row["ID"]
        for row in rows
        if row["EVENT_ID"].startswith(prefix)
    ]


# 创建 5 种状态的测试任务
pending_id = create_task("PENDING")
retry_due_id = create_task("RETRY_DUE")
retry_future_id = create_task("RETRY_FUTURE")
sending_id = create_task("SENDING")
sent_id = create_task("SENT")
dead_id = create_task("DEAD")

set_task_state(retry_due_id, "RETRY", -60)
set_task_state(retry_future_id, "RETRY", 3600)
set_task_state(sending_id, "SENDING")
set_task_state(sent_id, "SENT")
set_task_state(dead_id, "DEAD")


# 1. 返回列表
rows = repo.get_due_notifications(limit=100)
assert isinstance(rows, list)
print("[TEST] RETURNS_LIST= True")


# 2. PENDING 被发现
ids = discover_test_ids()
assert pending_id in ids
print("[TEST] PENDING_DISCOVERED= True")


# 3. 到期 RETRY 被发现
assert retry_due_id in ids
print("[TEST] DUE_RETRY_DISCOVERED= True")


# 4. 未到期 RETRY 不返回
assert retry_future_id not in ids
print("[TEST] FUTURE_RETRY_EXCLUDED= True")


# 5. SENDING 不返回
assert sending_id not in ids
print("[TEST] SENDING_EXCLUDED= True")


# 6. SENT 不返回
assert sent_id not in ids
print("[TEST] SENT_EXCLUDED= True")


# 7. DEAD 不返回
assert dead_id not in ids
print("[TEST] DEAD_EXCLUDED= True")


# 8. 查询不修改状态
connection = get_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ID, STATUS
            FROM WEBHOOK_NOTIFICATION_OUTBOX
            WHERE ID IN (%s, %s)
            """,
            (pending_id, retry_due_id),
        )

        state_rows = cursor.fetchall()

        states = {}

        for row in state_rows:
            if isinstance(row, dict):
                states[row["ID"]] = row["STATUS"]
            else:
                states[row[0]] = row[1]

finally:
    connection.close()

assert states[pending_id] == "PENDING"
assert states[retry_due_id] == "RETRY"

print("[TEST] DISCOVERY_READ_ONLY= True")


# 9. 非法 limit
for invalid_limit in (
    0, -1, 101, None, "10", True
):
    try:
        repo.get_due_notifications(invalid_limit)
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid_limit!r}"
    )

print("[TEST] INVALID_LIMIT_REJECTED= True")


print("[INFO] DISCOVERED_TEST_IDS=", ids)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox due discovery"
)
