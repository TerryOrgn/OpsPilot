
from webhook_notification_recovery_worker import (
    WebhookNotificationRecoveryWorker,
)


def make_task(notification_id, token="token"):
    return {
        "ID": notification_id,
        "CLAIM_TOKEN": token,
    }


class FakeRecoveryRepository:
    """
    模拟不同恢复结果。

    不访问 MySQL。
    不修改真实任务。
    """

    def __init__(self, tasks, outcomes=None):
        self.tasks = list(tasks)
        self.outcomes = outcomes or {}
        self.calls = []

    def get_expired_lease_notifications(self, limit=100):
        return self.tasks[:limit]

    def recover_expired_lease(
        self,
        notification_id,
        expected_claim_token,
        retry_delay_seconds=60,
    ):
        self.calls.append(notification_id)

        outcome = self.outcomes.get(
            notification_id,
            "RECOVERED_RETRY",
        )

        if isinstance(outcome, Exception):
            raise outcome

        return {
            "notification_id": notification_id,
            "event_type": outcome,
            "retry_count": 1,
        }


# --------------------------------------------------
# 1. 单任务异常不影响后续任务
# --------------------------------------------------

repo = FakeRecoveryRepository(
    tasks=[
        make_task(101),
        make_task(102),
        make_task(103),
    ],
    outcomes={
        101: RuntimeError("Simulated database error"),
        102: "RECOVERED_RETRY",
        103: "RECOVERED_DEAD",
    },
)

worker = WebhookNotificationRecoveryWorker(
    repository=repo
)

stats = worker.run_once()

assert stats["discovered"] == 3
assert stats["errors"] == 1
assert stats["recovered_retry"] == 1
assert stats["recovered_dead"] == 1

print("[TEST] SINGLE_TASK_ERROR_ISOLATED= True")


# --------------------------------------------------
# 2. 异常后仍继续执行剩余任务
# --------------------------------------------------

assert repo.calls == [101, 102, 103]

print("[TEST] CONTINUES_AFTER_ERROR= True")


# --------------------------------------------------
# 3. 并发竞争失败正确计入 skipped
# --------------------------------------------------

repo = FakeRecoveryRepository(
    tasks=[
        make_task(201),
        make_task(202),
    ],
    outcomes={
        201: "NOT_RECOVERED",
        202: "RECOVERED_RETRY",
    },
)

stats = WebhookNotificationRecoveryWorker(
    repository=repo
).run_once()

assert stats["discovered"] == 2
assert stats["skipped"] == 1
assert stats["recovered_retry"] == 1
assert stats["errors"] == 0

print("[TEST] OWNERSHIP_RACE_SKIPPED= True")


# --------------------------------------------------
# 4. 缺失 Token 安全跳过
# --------------------------------------------------

repo = FakeRecoveryRepository(
    tasks=[
        make_task(301, None),
        make_task(302, ""),
        make_task(303, "valid-token"),
    ],
)

stats = WebhookNotificationRecoveryWorker(
    repository=repo
).run_once()

assert stats["discovered"] == 3
assert stats["skipped"] == 2
assert stats["recovered_retry"] == 1

assert repo.calls == [303]

print("[TEST] MISSING_TOKEN_SKIPPED= True")


# --------------------------------------------------
# 5. 扫描异常必须向上抛出
# --------------------------------------------------

class FailingScanRepository:

    def get_expired_lease_notifications(self, limit=100):
        raise ConnectionError(
            "Simulated MySQL connection failure"
        )


worker = WebhookNotificationRecoveryWorker(
    repository=FailingScanRepository()
)

try:
    worker.run_once()

except ConnectionError:
    print("[TEST] SCAN_ERROR_PROPAGATED= True")

else:
    raise AssertionError(
        "Scan error must propagate"
    )


# --------------------------------------------------
# 6. 第二轮不能重复恢复
# --------------------------------------------------

class StatefulFakeRepository:

    def __init__(self):
        self.tasks = [
            make_task(401, "token-401")
        ]
        self.recovery_count = 0

    def get_expired_lease_notifications(self, limit=100):
        return self.tasks[:limit]

    def recover_expired_lease(
        self,
        notification_id,
        expected_claim_token,
        retry_delay_seconds=60,
    ):
        self.recovery_count += 1

        # 模拟数据库原子恢复后，
        # 任务不再属于过期 SENDING 集合。
        self.tasks = []

        return {
            "notification_id": notification_id,
            "event_type": "RECOVERED_RETRY",
            "retry_count": 1,
        }


repo = StatefulFakeRepository()

worker = WebhookNotificationRecoveryWorker(
    repository=repo
)

first = worker.run_once()
second = worker.run_once()

assert first["recovered_retry"] == 1
assert second["discovered"] == 0
assert second["recovered_retry"] == 0
assert repo.recovery_count == 1

print("[TEST] SECOND_RUN_NO_DUPLICATE= True")


# --------------------------------------------------
# 7. 非法 retry_delay_seconds
# --------------------------------------------------

worker = WebhookNotificationRecoveryWorker(
    repository=FakeRecoveryRepository([])
)

for invalid in (-1, None, True, 1.5, "60"):
    try:
        worker.run_once(
            retry_delay_seconds=invalid
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_RETRY_DELAY_REJECTED= True")


# --------------------------------------------------
# 8. 未知恢复结果被记录为 errors
# --------------------------------------------------

repo = FakeRecoveryRepository(
    tasks=[
        make_task(501),
        make_task(502),
    ],
    outcomes={
        501: "UNKNOWN_RESULT",
        502: "RECOVERED_RETRY",
    },
)

stats = WebhookNotificationRecoveryWorker(
    repository=repo
).run_once()

assert stats["errors"] == 1
assert stats["recovered_retry"] == 1
assert repo.calls == [501, 502]

print("[TEST] UNKNOWN_RESULT_ISOLATED= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery worker resilience"
)
