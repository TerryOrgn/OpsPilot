
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repository = WebhookNotificationOutboxRepository()

event_id = f"TEST-92-57-E-{uuid4().hex}"

created = repository.create_notification(
    event_id=event_id,
    alert_key="TEST-92-57-E:WEBHOOK_ERROR_RATE",
    event_type="CREATED",
    payload="Test Outbox mark_sent lifecycle",
)

notification_id = created["notification_id"]


def get_row():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    SENT_AT,
                    RETRY_COUNT,
                    LAST_ERROR,
                    NEXT_RETRY_AT
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise AssertionError(
                    "Notification not found"
                )

            if isinstance(row, dict):
                return row

            columns = [
                item[0] for item in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


# 1. 新建任务为 PENDING
assert created["event_type"] == "CREATED"
assert get_row()["STATUS"] == "PENDING"

print("[TEST] INITIAL_PENDING= True")


# 2. 不允许 PENDING 直接变为 SENT
result = repository.mark_sent(notification_id)

assert result["event_type"] == "NOT_UPDATED"
assert get_row()["STATUS"] == "PENDING"

print("[TEST] PENDING_CANNOT_MARK_SENT= True")


# 3. Worker 领取任务
claimed = repository.claim_notification(
    notification_id
)

assert claimed["event_type"] == "CLAIMED"
assert get_row()["STATUS"] == "SENDING"

print("[TEST] CLAIMED_SENDING= True")


# 4. 成功确认发送
result = repository.mark_sent(notification_id)

assert result["event_type"] == "MARKED_SENT"

row = get_row()

assert row["STATUS"] == "SENT"
assert row["SENT_AT"] is not None

print("[TEST] SENDING_TO_SENT= True")


# 5. 保存首次确认时间
first_sent_at = row["SENT_AT"]

# 再次确认，不应修改状态和时间
result = repository.mark_sent(notification_id)

assert result["event_type"] == "NOT_UPDATED"

row = get_row()

assert row["STATUS"] == "SENT"
assert row["SENT_AT"] == first_sent_at

print("[TEST] REPEATED_MARK_SENT_IDEMPOTENT= True")


# 6. 已发送任务不能再次领取
result = repository.claim_notification(
    notification_id
)

assert result["event_type"] == "NOT_CLAIMED"

print("[TEST] SENT_CANNOT_BE_CLAIMED= True")


# 7. 不存在的 ID
result = repository.mark_sent(
    922570000000000001
)

assert result["event_type"] == "NOT_UPDATED"

print("[TEST] NONEXISTENT_ID_NOT_UPDATED= True")


# 8. 非法 ID
for invalid_id in (0, -1, None, "123", True):
    try:
        repository.mark_sent(invalid_id)

    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError for {invalid_id!r}"
    )

print("[TEST] INVALID_ID_REJECTED= True")


# 9. 确认其他字段没有异常变化
row = get_row()

assert row["RETRY_COUNT"] == 0
assert row["LAST_ERROR"] is None
assert row["NEXT_RETRY_AT"] is None

print("[TEST] OTHER_FIELDS_CORRECT= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox mark sent"
)
