
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-Q-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-Q:{name}",
        event_type="CREATED",
        payload=f"Legacy API disabled test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id, claimed["claim_token"]


def get_state(notification_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
                    CLAIM_TOKEN
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


# 1. 旧 mark_sent 必须拒绝执行
sent_id, sent_token = create_and_claim("SENT")

try:
    repo.mark_sent(sent_id)
except RuntimeError as error:
    assert "mark_sent_with_token" in str(error)
else:
    raise AssertionError(
        "Legacy mark_sent should be disabled"
    )

print("[TEST] LEGACY_MARK_SENT_DISABLED= True")


# 2. 拒绝调用后数据库状态不变
sent_state = get_state(sent_id)

assert sent_state["STATUS"] == "SENDING"
assert sent_state["CLAIM_TOKEN"] == sent_token

print("[TEST] LEGACY_SENT_NO_MUTATION= True")


# 3. 旧 mark_failed 必须拒绝执行
failed_id, failed_token = create_and_claim("FAILED")

try:
    repo.mark_failed(
        failed_id,
        "Legacy failure attempt",
    )
except RuntimeError as error:
    assert "mark_failed_with_token" in str(error)
else:
    raise AssertionError(
        "Legacy mark_failed should be disabled"
    )

print("[TEST] LEGACY_MARK_FAILED_DISABLED= True")


# 4. 拒绝调用后失败次数不变
failed_state = get_state(failed_id)

assert failed_state["STATUS"] == "SENDING"
assert failed_state["RETRY_COUNT"] == 0
assert failed_state["CLAIM_TOKEN"] == failed_token

print("[TEST] LEGACY_FAILED_NO_MUTATION= True")


# 5. 新版成功接口仍然正常
sent_result = repo.mark_sent_with_token(
    sent_id,
    sent_token,
)

assert sent_result["event_type"] == "MARKED_SENT"
assert get_state(sent_id)["STATUS"] == "SENT"

print("[TEST] SAFE_MARK_SENT_WORKS= True")


# 6. 新版失败接口仍然正常
failed_result = repo.mark_failed_with_token(
    failed_id,
    failed_token,
    "Simulated failure",
    retry_delay_seconds=60,
)

assert failed_result["event_type"] == "RETRY_SCHEDULED"

failed_state = get_state(failed_id)

assert failed_state["STATUS"] == "RETRY"
assert failed_state["RETRY_COUNT"] == 1

print("[TEST] SAFE_MARK_FAILED_WORKS= True")


# 7. 安全接口完成后 Token 清除
assert get_state(sent_id)["CLAIM_TOKEN"] is None
assert get_state(failed_id)["CLAIM_TOKEN"] is None

print("[TEST] SAFE_COMPLETION_CLEARS_TOKEN= True")


print("[INFO] SENT_ID=", sent_id)
print("[INFO] FAILED_ID=", failed_id)

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox legacy API disabled"
)
