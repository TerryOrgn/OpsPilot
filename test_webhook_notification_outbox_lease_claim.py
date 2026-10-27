
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-M-{uuid4().hex}"


def create_task(name):
    result = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-M:{name}",
        event_type="CREATED",
        payload=f"Lease claim test: {name}",
    )

    return result["notification_id"]


def get_row(notification_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    CLAIMED_AT,
                    LEASE_EXPIRES_AT,
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


# 1. 创建任务并领取
notification_id = create_task("NORMAL")

result = repo.claim_notification(
    notification_id,
    lease_seconds=300,
)

assert result["event_type"] == "CLAIMED"

print("[TEST] CLAIM_SUCCESS= True")


# 2. 返回有效 Token
token = result["claim_token"]

assert isinstance(token, str)
assert len(token) == 32

print("[TEST] CLAIM_TOKEN_RETURNED= True")


# 3. 数据库保存 Token
row = get_row(notification_id)

assert row["STATUS"] == "SENDING"
assert row["CLAIM_TOKEN"] == token

print("[TEST] CLAIM_TOKEN_PERSISTED= True")


# 4. 租约时间正确
assert isinstance(row["CLAIMED_AT"], datetime)
assert isinstance(row["LEASE_EXPIRES_AT"], datetime)

duration = (
    row["LEASE_EXPIRES_AT"] - row["CLAIMED_AT"]
).total_seconds()

assert abs(duration - 300) < 1

assert (
    result["lease_expires_at"]
    == row["LEASE_EXPIRES_AT"]
)

print("[TEST] LEASE_DURATION_CORRECT= True")


# 5. 重复领取被拒绝
second = repo.claim_notification(notification_id)

assert second["event_type"] == "NOT_CLAIMED"
assert second["claim_token"] is None
assert second["lease_expires_at"] is None

print("[TEST] DUPLICATE_CLAIM_REJECTED= True")


# 6. 重复领取不能覆盖原 Token
after_duplicate = get_row(notification_id)

assert after_duplicate["CLAIM_TOKEN"] == token

print("[TEST] TOKEN_NOT_OVERWRITTEN= True")


# 7. 并发竞争
concurrent_id = create_task("CONCURRENT")


def attempt_claim(_):
    return repo.claim_notification(
        concurrent_id,
        lease_seconds=300,
    )


with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(
        attempt_claim,
        range(10),
    ))

claimed = [
    result
    for result in results
    if result["event_type"] == "CLAIMED"
]

not_claimed = [
    result
    for result in results
    if result["event_type"] == "NOT_CLAIMED"
]

assert len(claimed) == 1
assert len(not_claimed) == 9

print("[TEST] CONCURRENT_SINGLE_WINNER= True")


# 8. 只有获胜者拥有有效 Token
assert claimed[0]["claim_token"] is not None

assert all(
    item["claim_token"] is None
    for item in not_claimed
)

concurrent_row = get_row(concurrent_id)

assert (
    concurrent_row["CLAIM_TOKEN"]
    == claimed[0]["claim_token"]
)

print("[TEST] ONLY_WINNER_HAS_TOKEN= True")


# 9. 非法 Lease 参数
for invalid in (0, -1, None, "300", True):
    try:
        repo.claim_notification(
            notification_id,
            lease_seconds=invalid,
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_LEASE_REJECTED= True")


print("[INFO] NORMAL_ID=", notification_id)
print("[INFO] CONCURRENT_ID=", concurrent_id)
print("[INFO] CONCURRENT_WINNERS=", len(claimed))

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox lease claim"
)
