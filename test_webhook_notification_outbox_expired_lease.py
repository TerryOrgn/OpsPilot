
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-R-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-R:{name}",
        event_type="CREATED",
        payload=f"Expired lease test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id


def set_lease(notification_id, expression):
    """
    expression 只允许测试内固定的 SQL 表达式。
    不接受外部输入。
    """

    allowed = {
        "EXPIRED": (
            "DATE_SUB(CURRENT_TIMESTAMP(6), "
            "INTERVAL 10 SECOND)"
        ),
        "VALID": (
            "DATE_ADD(CURRENT_TIMESTAMP(6), "
            "INTERVAL 300 SECOND)"
        ),
        "NULL": "NULL",
    }

    if expression not in allowed:
        raise ValueError("Invalid test lease expression")

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                SET LEASE_EXPIRES_AT = {allowed[expression]}
                WHERE ID = %s
                """,
                (notification_id,),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def get_status(notification_id):
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

            return (
                row["STATUS"]
                if isinstance(row, dict)
                else row[0]
            )

    finally:
        connection.close()


# 创建四个不同状态的任务
expired_id = create_and_claim("EXPIRED")
valid_id = create_and_claim("VALID")
null_id = create_and_claim("NULL")
sent_id = create_and_claim("SENT")

set_lease(expired_id, "EXPIRED")
set_lease(valid_id, "VALID")
set_lease(null_id, "NULL")

# SENT 任务即使 Lease 时间过期，也不能被识别
sent_claim = repo.get_expired_lease_notifications(
    limit=100
)

# 先将 SENT 测试任务正常完成
# 使用原本领取的 Token 需要重新获取：
# 因此这里直接通过受控测试 SQL 设置状态，
# 仅限本测试新建的任务。
connection = get_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE WEBHOOK_NOTIFICATION_OUTBOX
            SET
                STATUS = 'SENT',
                LEASE_EXPIRES_AT = DATE_SUB(
                    CURRENT_TIMESTAMP(6),
                    INTERVAL 10 SECOND
                )
            WHERE ID = %s
            """,
            (sent_id,),
        )

    connection.commit()

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()


# 1. 获取过期任务
rows = repo.get_expired_lease_notifications(limit=100)

ids = {row["ID"] for row in rows}

assert expired_id in ids

print("[TEST] EXPIRED_LEASE_DETECTED= True")


# 2. 有效 Lease 不应该出现
assert valid_id not in ids

print("[TEST] VALID_LEASE_EXCLUDED= True")


# 3. NULL Lease 不应该出现
assert null_id not in ids

print("[TEST] NULL_LEASE_EXCLUDED= True")


# 4. 非 SENDING 任务不应该出现
assert sent_id not in ids

print("[TEST] NON_SENDING_EXCLUDED= True")


# 5. 查询不会修改状态
assert get_status(expired_id) == "SENDING"

print("[TEST] READ_ONLY_NO_MUTATION= True")


# 6. 返回必要字段
expired_row = next(
    row for row in rows
    if row["ID"] == expired_id
)

required_fields = {
    "ID",
    "EVENT_ID",
    "STATUS",
    "RETRY_COUNT",
    "MAX_RETRIES",
    "CLAIMED_AT",
    "LEASE_EXPIRES_AT",
    "CLAIM_TOKEN",
}

assert required_fields.issubset(expired_row.keys())

print("[TEST] REQUIRED_FIELDS_PRESENT= True")


# 7. 非法 limit 参数
for invalid in (0, -1, 101, None, True, "10"):
    try:
        repo.get_expired_lease_notifications(
            limit=invalid
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_LIMIT_REJECTED= True")


print("[INFO] EXPIRED_ID=", expired_id)
print("[INFO] VALID_ID=", valid_id)
print("[INFO] NULL_ID=", null_id)
print("[INFO] SENT_ID=", sent_id)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox expired lease detection"
)
