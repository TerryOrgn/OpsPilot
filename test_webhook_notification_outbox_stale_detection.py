
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()

prefix = f"TEST-92-57-K-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-K:{name}",
        event_type="CREATED",
        payload=f"Stale detection test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(notification_id)

    assert claimed["event_type"] == "CLAIMED"

    return notification_id


def get_row(notification_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT STATUS, UPDATED_AT, RETRY_COUNT
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )

            row = cursor.fetchone()

            if isinstance(row, dict):
                return row

            columns = [
                item[0] for item in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


stale_id = create_and_claim("STALE")
fresh_id = create_and_claim("FRESH")


# 1. 初始状态均为 SENDING
assert get_row(stale_id)["STATUS"] == "SENDING"
assert get_row(fresh_id)["STATUS"] == "SENDING"

print("[TEST] BOTH_SENDING= True")


# 2. 模拟一条任务已卡住 10 分钟
connection = get_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE WEBHOOK_NOTIFICATION_OUTBOX
            SET UPDATED_AT = DATE_SUB(
                CURRENT_TIMESTAMP(6),
                INTERVAL 600 SECOND
            )
            WHERE ID = %s
              AND STATUS = 'SENDING'
            """,
            (stale_id,),
        )

        assert cursor.rowcount == 1

    connection.commit()

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()


# 3. 查询超时任务
rows = repo.get_stale_sending_notifications(
    timeout_seconds=300,
    limit=100,
)

ids = {row["ID"] for row in rows}


# 4. 超时任务被识别
assert stale_id in ids
print("[TEST] STALE_DETECTED= True")


# 5. 正常任务未被识别
assert fresh_id not in ids
print("[TEST] FRESH_EXCLUDED= True")


# 6. 查询不修改状态
assert get_row(stale_id)["STATUS"] == "SENDING"
assert get_row(fresh_id)["STATUS"] == "SENDING"

print("[TEST] DETECTION_READ_ONLY= True")


# 7. RETRY_COUNT 不改变
assert get_row(stale_id)["RETRY_COUNT"] == 0
assert get_row(fresh_id)["RETRY_COUNT"] == 0

print("[TEST] RETRY_COUNT_UNCHANGED= True")


# 8. 非法 timeout 参数
for invalid in (0, -1, None, "300", True):
    try:
        repo.get_stale_sending_notifications(
            timeout_seconds=invalid
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError for {invalid!r}"
    )

print("[TEST] INVALID_TIMEOUT_REJECTED= True")


# 9. 非法 limit 参数
for invalid in (0, -1, 101, None, "10", True):
    try:
        repo.get_stale_sending_notifications(
            limit=invalid
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError for {invalid!r}"
    )

print("[TEST] INVALID_LIMIT_REJECTED= True")


print("[INFO] STALE_ID=", stale_id)
print("[INFO] FRESH_ID=", fresh_id)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox stale detection"
)
