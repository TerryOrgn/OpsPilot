
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()
prefix = f"TEST-92-57-S-{uuid4().hex}"


def create_and_claim(name):
    created = repo.create_notification(
        event_id=f"{prefix}-{name}",
        alert_key=f"TEST-92-57-S:{name}",
        event_type="CREATED",
        payload=f"Atomic recovery test: {name}",
    )

    notification_id = created["notification_id"]

    claimed = repo.claim_notification(
        notification_id,
        lease_seconds=300,
    )

    assert claimed["event_type"] == "CLAIMED"

    return notification_id, claimed["claim_token"]


def execute_sql(sql, params):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def expire_lease(notification_id):
    execute_sql(
        """
        UPDATE WEBHOOK_NOTIFICATION_OUTBOX
        SET LEASE_EXPIRES_AT = DATE_SUB(
            CURRENT_TIMESTAMP(6),
            INTERVAL 10 SECOND
        )
        WHERE ID = %s
        """,
        (notification_id,),
    )


def get_row(notification_id):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    STATUS,
                    RETRY_COUNT,
                    MAX_RETRIES,
                    CLAIM_TOKEN,
                    CLAIMED_AT,
                    LEASE_EXPIRES_AT,
                    NEXT_RETRY_AT,
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


# 1. 正常恢复过期 Lease
normal_id, normal_token = create_and_claim("NORMAL")
expire_lease(normal_id)

normal_result = repo.recover_expired_lease(
    normal_id,
    normal_token,
    retry_delay_seconds=60,
)

assert normal_result["event_type"] == "RECOVERED_RETRY"

print("[TEST] EXPIRED_LEASE_RECOVERED= True")


# 2. 恢复后进入 RETRY，重试次数增加
normal_row = get_row(normal_id)

assert normal_row["STATUS"] == "RETRY"
assert normal_row["RETRY_COUNT"] == 1
assert normal_row["NEXT_RETRY_AT"] is not None

print("[TEST] RECOVERY_SCHEDULES_RETRY= True")


# 3. 旧所有权被清除
assert normal_row["CLAIM_TOKEN"] is None
assert normal_row["CLAIMED_AT"] is None
assert normal_row["LEASE_EXPIRES_AT"] is None

print("[TEST] OLD_OWNERSHIP_CLEARED= True")


# 4. 旧 Worker 无法确认发送成功
old_worker_result = repo.mark_sent_with_token(
    normal_id,
    normal_token,
)

assert old_worker_result["event_type"] == "NOT_UPDATED"
assert get_row(normal_id)["STATUS"] == "RETRY"

print("[TEST] OLD_WORKER_REJECTED= True")


# 5. 有效 Lease 不允许恢复
valid_id, valid_token = create_and_claim("VALID")

valid_result = repo.recover_expired_lease(
    valid_id,
    valid_token,
)

assert valid_result["event_type"] == "NOT_RECOVERED"
assert get_row(valid_id)["STATUS"] == "SENDING"

print("[TEST] VALID_LEASE_NOT_RECOVERED= True")


# 6. 错误 Token 不允许恢复
wrong_id, wrong_token = create_and_claim("WRONG")
expire_lease(wrong_id)

wrong_result = repo.recover_expired_lease(
    wrong_id,
    "incorrect-token",
)

assert wrong_result["event_type"] == "NOT_RECOVERED"
assert get_row(wrong_id)["CLAIM_TOKEN"] == wrong_token

print("[TEST] WRONG_TOKEN_NOT_RECOVERED= True")


# 7. 并发恢复只允许一个成功
concurrent_id, concurrent_token = create_and_claim(
    "CONCURRENT"
)

expire_lease(concurrent_id)


def attempt_recovery(_):
    return repo.recover_expired_lease(
        concurrent_id,
        concurrent_token,
        retry_delay_seconds=60,
    )


with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(
        executor.map(attempt_recovery, range(10))
    )

recovered = [
    item
    for item in results
    if item["event_type"] == "RECOVERED_RETRY"
]

rejected = [
    item
    for item in results
    if item["event_type"] == "NOT_RECOVERED"
]

assert len(recovered) == 1
assert len(rejected) == 9

print("[TEST] CONCURRENT_SINGLE_RECOVERY= True")


# 8. 并发恢复不能重复增加重试次数
concurrent_row = get_row(concurrent_id)

assert concurrent_row["RETRY_COUNT"] == 1
assert concurrent_row["STATUS"] == "RETRY"

print("[TEST] RECOVERY_COUNT_NOT_DUPLICATED= True")


# 9. 达到最大重试次数进入 DEAD
dead_id, dead_token = create_and_claim("DEAD")

execute_sql(
    """
    UPDATE WEBHOOK_NOTIFICATION_OUTBOX
    SET
        RETRY_COUNT = MAX_RETRIES - 1,
        LEASE_EXPIRES_AT = DATE_SUB(
            CURRENT_TIMESTAMP(6),
            INTERVAL 10 SECOND
        )
    WHERE ID = %s
    """,
    (dead_id,),
)

dead_result = repo.recover_expired_lease(
    dead_id,
    dead_token,
)

dead_row = get_row(dead_id)

assert dead_result["event_type"] == "RECOVERED_DEAD"
assert dead_row["STATUS"] == "DEAD"
assert dead_row["RETRY_COUNT"] == dead_row["MAX_RETRIES"]
assert dead_row["NEXT_RETRY_AT"] is None

print("[TEST] MAX_RETRIES_RECOVERS_TO_DEAD= True")


# 10. 非法参数
for invalid in ("", " ", None, 123):
    try:
        repo.recover_expired_lease(
            normal_id,
            invalid,
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_TOKEN_REJECTED= True")


print("[INFO] NORMAL_ID=", normal_id)
print("[INFO] CONCURRENT_ID=", concurrent_id)
print("[INFO] DEAD_ID=", dead_id)
print("[INFO] RECOVERY_WINNERS=", len(recovered))

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox atomic recovery"
)
