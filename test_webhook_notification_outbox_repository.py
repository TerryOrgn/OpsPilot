
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repository = WebhookNotificationOutboxRepository()

event_id = f"TEST-92-57-B-{uuid4().hex}"

alert_key = "TEST-92-57-B:WEBHOOK_ERROR_RATE"

payload = "Webhook error rate exceeded threshold"


def get_rows(event_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ID,
                    EVENT_ID,
                    ALERT_KEY,
                    EVENT_TYPE,
                    CHANNEL,
                    PAYLOAD,
                    STATUS,
                    RETRY_COUNT,
                    MAX_RETRIES
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE EVENT_ID = %s
                """,
                (event_id,),
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


# 1. 第一次插入
first = repository.create_notification(
    event_id=event_id,
    alert_key=alert_key,
    event_type="CREATED",
    payload=payload,
)

assert first["event_type"] == "CREATED"
assert first["notification_id"] is not None

print("[TEST] FIRST_CREATED= True")


# 2. 第二次插入相同 EVENT_ID
second = repository.create_notification(
    event_id=event_id,
    alert_key=alert_key,
    event_type="CREATED",
    payload=payload,
)

assert second["event_type"] == "DUPLICATE"

print("[TEST] SECOND_DUPLICATE= True")


# 3. 两次返回同一个数据库 ID
assert (
    first["notification_id"]
    == second["notification_id"]
)

print("[TEST] SAME_NOTIFICATION_ID= True")


# 4. 数据库只有一条记录
rows = get_rows(event_id)

assert len(rows) == 1

print("[TEST] ONLY_ONE_ROW= True")


# 5. 检查数据库默认状态
row = rows[0]

assert row["STATUS"] == "PENDING"
assert row["RETRY_COUNT"] == 0
assert row["MAX_RETRIES"] == 3
assert row["CHANNEL"] == "MOCK"

print("[TEST] DEFAULT_STATUS= True")


# 6. 检查业务字段
assert row["EVENT_ID"] == event_id
assert row["ALERT_KEY"] == alert_key
assert row["EVENT_TYPE"] == "CREATED"
assert row["PAYLOAD"] == payload

print("[TEST] BUSINESS_FIELDS= True")


# 7. 非法 EVENT_TYPE
try:
    repository.create_notification(
        event_id=f"INVALID-{uuid4().hex}",
        alert_key=alert_key,
        event_type="UNKNOWN",
        payload=payload,
    )

    raise AssertionError("Expected ValueError")

except ValueError:
    print("[TEST] INVALID_EVENT_TYPE= True")


# 8. 空 EVENT_ID
try:
    repository.create_notification(
        event_id="",
        alert_key=alert_key,
        event_type="CREATED",
        payload=payload,
    )

    raise AssertionError("Expected ValueError")

except ValueError:
    print("[TEST] EMPTY_EVENT_ID= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox repository"
)
