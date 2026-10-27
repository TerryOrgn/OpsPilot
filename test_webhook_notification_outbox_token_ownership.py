
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-N-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-N:{name}",
        event_type="CREATED",
        payload=f"Token ownership test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id, claimed["claim_token"]


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
                item[0]
                for item in cursor.description
            ]

            return dict(zip(columns, row))

    finally:
        connection.close()


# 1. 正确 Token 可以确认成功
sent_id, sent_token = create_and_claim("SENT")

result = repo.mark_sent_with_token(
    sent_id,
    sent_token,
)

assert result["event_type"] == "MARKED_SENT"
assert get_row(sent_id)["STATUS"] == "SENT"

print("[TEST] VALID_TOKEN_MARKS_SENT= True")


# 2. SENT 后清除所有权
sent_row = get_row(sent_id)

assert sent_row["CLAIM_TOKEN"] is None
assert sent_row["LEASE_EXPIRES_AT"] is None
assert sent_row["SENT_AT"] is not None

print("[TEST] SENT_CLEARS_LEASE= True")


# 3. 错误 Token 无法确认成功
wrong_id, correct_token = create_and_claim("WRONG")

wrong_result = repo.mark_sent_with_token(
    wrong_id,
    "incorrect-token",
)

assert wrong_result["event_type"] == "NOT_UPDATED"
assert get_row(wrong_id)["STATUS"] == "SENDING"
assert get_row(wrong_id)["CLAIM_TOKEN"] == correct_token

print("[TEST] WRONG_TOKEN_REJECTED= True")


# 4. 正确 Token 可以安排重试
retry_id, retry_token = create_and_claim("RETRY")

retry_result = repo.mark_failed_with_token(
    retry_id,
    retry_token,
    "Simulated failure",
    retry_delay_seconds=60,
)

retry_row = get_row(retry_id)

assert retry_result["event_type"] == "RETRY_SCHEDULED"
assert retry_row["STATUS"] == "RETRY"
assert retry_row["RETRY_COUNT"] == 1

print("[TEST] VALID_TOKEN_SCHEDULES_RETRY= True")


# 5. RETRY 后清除 Lease
assert retry_row["CLAIM_TOKEN"] is None
assert retry_row["LEASE_EXPIRES_AT"] is None

print("[TEST] RETRY_CLEARS_LEASE= True")


# 6. 错误 Token 无法修改失败状态
failure_id, failure_token = create_and_claim(
    "WRONG-FAILURE"
)

failure_result = repo.mark_failed_with_token(
    failure_id,
    "incorrect-token",
    "Should not update",
)

assert failure_result["event_type"] == "NOT_UPDATED"
assert get_row(failure_id)["STATUS"] == "SENDING"
assert get_row(failure_id)["RETRY_COUNT"] == 0
assert get_row(failure_id)["CLAIM_TOKEN"] == failure_token

print("[TEST] WRONG_TOKEN_CANNOT_FAIL= True")


# 7. 模拟租约过期
expired_id, expired_token = create_and_claim(
    "EXPIRED"
)

connection = get_connection()

try:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE WEBHOOK_NOTIFICATION_OUTBOX
            SET LEASE_EXPIRES_AT = DATE_SUB(
                CURRENT_TIMESTAMP(6),
                INTERVAL 1 SECOND
            )
            WHERE ID = %s
            """,
            (expired_id,),
        )

    connection.commit()

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()


# 8. 过期 Token 不能确认成功
expired_sent = repo.mark_sent_with_token(
    expired_id,
    expired_token,
)

assert expired_sent["event_type"] == "NOT_UPDATED"
assert get_row(expired_id)["STATUS"] == "SENDING"

print("[TEST] EXPIRED_TOKEN_CANNOT_SEND= True")


# 9. 过期 Token 不能安排重试
expired_failed = repo.mark_failed_with_token(
    expired_id,
    expired_token,
    "Expired worker failure",
)

assert expired_failed["event_type"] == "NOT_UPDATED"
assert get_row(expired_id)["RETRY_COUNT"] == 0

print("[TEST] EXPIRED_TOKEN_CANNOT_FAIL= True")


# 10. 非法 Token 参数被拒绝
for invalid in ("", " ", None, 123):
    try:
        repo.mark_sent_with_token(
            wrong_id,
            invalid,
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError for {invalid!r}"
    )

print("[TEST] INVALID_TOKEN_REJECTED= True")


print("[INFO] SENT_ID=", sent_id)
print("[INFO] RETRY_ID=", retry_id)
print("[INFO] EXPIRED_ID=", expired_id)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox token ownership"
)
