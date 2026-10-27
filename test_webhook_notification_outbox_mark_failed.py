
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()

created = repo.create_notification(
    event_id=f"TEST-92-57-F-{uuid4().hex}",
    alert_key="TEST-92-57-F:WEBHOOK_ERROR_RATE",
    event_type="CREATED",
    payload="Test notification failure retry",
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
                    RETRY_COUNT,
                    MAX_RETRIES,
                    NEXT_RETRY_AT,
                    LAST_ERROR,
                    SENT_AT
                FROM WEBHOOK_NOTIFICATION_OUTBOX
                WHERE ID = %s
                """,
                (notification_id,),
            )
            row = cursor.fetchone()
            if isinstance(row, dict):
                return row
            columns = [c[0] for c in cursor.description]
            return dict(zip(columns, row))
    finally:
        connection.close()


def prepare_retry_for_test():
    """
    仅供测试使用。
    模拟重试时间已到，并将任务重新放回 PENDING。
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                SET STATUS = 'PENDING',
                    NEXT_RETRY_AT = NULL
                WHERE ID = %s
                  AND STATUS = 'RETRY'
                """,
                (notification_id,),
            )
            assert cursor.rowcount == 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# 1. 初始状态
assert get_row()["STATUS"] == "PENDING"
print("[TEST] INITIAL_PENDING= True")


# 2. PENDING 不能直接标记失败
result = repo.mark_failed(notification_id, "Network timeout")
assert result["event_type"] == "NOT_UPDATED"
assert get_row()["RETRY_COUNT"] == 0
print("[TEST] PENDING_CANNOT_FAIL= True")


# 3. 第一次失败
assert repo.claim_notification(
    notification_id
)["event_type"] == "CLAIMED"

result = repo.mark_failed(
    notification_id,
    "Teams API timeout",
)

row = get_row()

print("[DEBUG] FIRST_FAILURE_RESULT=", result)
print("[DEBUG] FIRST_FAILURE_DB=", row)

assert result["event_type"] == "RETRY_SCHEDULED"
assert row["STATUS"] == "RETRY"
assert row["RETRY_COUNT"] == 1
assert row["NEXT_RETRY_AT"] is not None
assert row["LAST_ERROR"] == "Teams API timeout"
print("[TEST] FIRST_FAILURE_RETRY= True")


# 4. 重复标记失败不增加计数
result = repo.mark_failed(
    notification_id,
    "Duplicate failure",
)
assert result["event_type"] == "NOT_UPDATED"
assert get_row()["RETRY_COUNT"] == 1
print("[TEST] DUPLICATE_FAILURE_IGNORED= True")


# 5. 第二次失败
prepare_retry_for_test()
assert repo.claim_notification(
    notification_id
)["event_type"] == "CLAIMED"

result = repo.mark_failed(
    notification_id,
    "Teams API unavailable",
)

row = get_row()
print("[DEBUG] SECOND_FAILURE_RESULT=", result)
print("[DEBUG] SECOND_FAILURE_DB=", row)
assert result["event_type"] == "RETRY_SCHEDULED"
assert row["STATUS"] == "RETRY"
assert row["RETRY_COUNT"] == 2
assert row["NEXT_RETRY_AT"] is not None
print("[TEST] SECOND_FAILURE_RETRY= True")


# 6. 第三次失败，进入 DEAD
prepare_retry_for_test()
assert repo.claim_notification(
    notification_id
)["event_type"] == "CLAIMED"

result = repo.mark_failed(
    notification_id,
    "Teams API still unavailable",
)

row = get_row()
assert result["event_type"] == "MARKED_DEAD"
assert row["STATUS"] == "DEAD"
assert row["RETRY_COUNT"] == 3
assert row["NEXT_RETRY_AT"] is None
assert row["SENT_AT"] is None
print("[TEST] THIRD_FAILURE_DEAD= True")


# 7. DEAD 不能再被领取
result = repo.claim_notification(notification_id)
assert result["event_type"] == "NOT_CLAIMED"
print("[TEST] DEAD_CANNOT_CLAIM= True")


# 8. DEAD 不允许继续累计失败
result = repo.mark_failed(
    notification_id,
    "Another failure",
)
assert result["event_type"] == "NOT_UPDATED"
assert get_row()["RETRY_COUNT"] == 3
print("[TEST] DEAD_FAILURE_IGNORED= True")


# 9. 非法参数
for invalid_id in (0, -1, None, "123", True):
    try:
        repo.mark_failed(invalid_id, "Error")
    except ValueError:
        continue
    raise AssertionError(f"Expected ValueError: {invalid_id!r}")

print("[TEST] INVALID_ID_REJECTED= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox mark failed"
)
