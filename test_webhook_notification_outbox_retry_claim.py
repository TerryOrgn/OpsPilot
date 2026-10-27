
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from db import get_connection
from webhook_notification_outbox_repository import (
    WebhookNotificationOutboxRepository,
)


repo = WebhookNotificationOutboxRepository()

created = repo.create_notification(
    event_id=f"TEST-92-57-G-{uuid4().hex}",
    alert_key="TEST-92-57-G:WEBHOOK_ERROR_RATE",
    event_type="CREATED",
    payload="Test retry claim",
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
                    NEXT_RETRY_AT
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


def make_retry_due_for_test():
    """
    仅修改测试任务的到期时间。
    不直接修改 STATUS。
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE WEBHOOK_NOTIFICATION_OUTBOX
                SET NEXT_RETRY_AT =
                    DATE_SUB(
                        CURRENT_TIMESTAMP(6),
                        INTERVAL 1 SECOND
                    )
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


# 1. 初始 PENDING
assert get_row()["STATUS"] == "PENDING"
print("[TEST] INITIAL_PENDING= True")


# 2. 第一次正常领取
result = repo.claim_notification(notification_id)
assert result["event_type"] == "CLAIMED"
assert get_row()["STATUS"] == "SENDING"
print("[TEST] INITIAL_CLAIMED= True")


# 3. 模拟发送失败，设置 1 小时后重试
result = repo.mark_failed(
    notification_id,
    "Temporary Teams API failure",
    retry_delay_seconds=3600,
)

row = get_row()
assert result["event_type"] == "RETRY_SCHEDULED"
assert row["STATUS"] == "RETRY"
assert row["RETRY_COUNT"] == 1
assert row["NEXT_RETRY_AT"] is not None
print("[TEST] RETRY_SCHEDULED= True")


# 4. 未到期不能领取
result = repo.claim_notification(notification_id)
assert result["event_type"] == "NOT_CLAIMED"
assert get_row()["STATUS"] == "RETRY"
print("[TEST] EARLY_RETRY_REJECTED= True")


# 5. 模拟重试时间已到
make_retry_due_for_test()
assert get_row()["STATUS"] == "RETRY"
print("[TEST] RETRY_DUE_PREPARED= True")


# 6. 10 个 Worker 并发领取
worker_count = 10
barrier = Barrier(worker_count)


def worker(index):
    barrier.wait(timeout=10)

    result = repo.claim_notification(notification_id)

    return index, result["event_type"]


with ThreadPoolExecutor(max_workers=worker_count) as executor:
    results = list(executor.map(worker, range(worker_count)))

claimed_count = sum(
    event == "CLAIMED"
    for _, event in results
)

not_claimed_count = sum(
    event == "NOT_CLAIMED"
    for _, event in results
)

assert claimed_count == 1
assert not_claimed_count == 9

print("[TEST] SINGLE_RETRY_WORKER_CLAIMED= True")


# 7. 领取后状态正确
row = get_row()

assert row["STATUS"] == "SENDING"
assert row["RETRY_COUNT"] == 1
assert row["NEXT_RETRY_AT"] is None

print("[TEST] RETRY_CLAIM_STATE_CORRECT= True")


# 8. 重复领取被拒绝
result = repo.claim_notification(notification_id)
assert result["event_type"] == "NOT_CLAIMED"

print("[TEST] REPEATED_CLAIM_REJECTED= True")


for index, event in sorted(results):
    print(f"[WORKER-{index}] event={event}")


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox retry claim"
)
