
from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)


class FakeRepository:

    def __init__(self):
        self.scan_calls = 0
        self.last_limit = None

    def get_expired_lease_notifications(self, limit=100):
        self.scan_calls += 1
        self.last_limit = limit

        tasks = [
            {"ID": 101, "CLAIM_TOKEN": "token-101"},
            {"ID": 102, "CLAIM_TOKEN": None},
            {"ID": 103, "CLAIM_TOKEN": "token-103"},
        ]

        return tasks[:limit]


class FakeWorker:

    def __init__(self):
        self.calls = 0
        self.last_limit = None
        self.last_retry_delay = None

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1
        self.last_limit = limit
        self.last_retry_delay = retry_delay_seconds

        return {
            "discovered": 2,
            "recovered_retry": 1,
            "recovered_dead": 1,
            "skipped": 0,
            "errors": 0,
        }


# 1. 默认禁止执行
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
)

result = guard.run_once()

assert result["event_type"] == "DISABLED"
assert repo.scan_calls == 0
assert worker.calls == 0

print("[TEST] DEFAULT_DISABLED= True")


# 2. 禁用状态下不访问数据库
assert result["discovered"] == 0
assert result["recovered_retry"] == 0

print("[TEST] DISABLED_NO_DB_ACCESS= True")


# 3. DRY_RUN 只扫描
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=True,
    dry_run=True,
)

result = guard.run_once()

assert result["event_type"] == "DRY_RUN"
assert result["discovered"] == 3
assert repo.scan_calls == 1
assert worker.calls == 0

print("[TEST] DRY_RUN_READ_ONLY= True")


# 4. 缺失 Token 统计
assert result["missing_token"] == 1

print("[TEST] MISSING_TOKEN_COUNTED= True")


# 5. DRY_RUN 批次限制
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=True,
    dry_run=True,
    max_batch_size=2,
)

result = guard.run_once()

assert result["discovered"] == 2
assert repo.last_limit == 2
assert worker.calls == 0

print("[TEST] DRY_RUN_BATCH_LIMIT= True")


# 6. 显式授权后允许执行
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=True,
    dry_run=False,
    max_batch_size=5,
    retry_delay_seconds=120,
)

result = guard.run_once()

assert result["event_type"] == "EXECUTED"
assert worker.calls == 1
assert worker.last_limit == 5
assert worker.last_retry_delay == 120

print("[TEST] EXPLICIT_EXECUTION_ALLOWED= True")


# 7. 执行统计正确返回
assert result["recovered_retry"] == 1
assert result["recovered_dead"] == 1
assert result["errors"] == 0

print("[TEST] EXECUTION_STATS_RETURNED= True")


# 8. 非法参数拒绝
invalid_cases = [
    {"enabled": "true"},
    {"dry_run": "false"},
    {"max_batch_size": 0},
    {"max_batch_size": 101},
    {"max_batch_size": True},
    {"retry_delay_seconds": -1},
    {"retry_delay_seconds": True},
]

for case in invalid_cases:
    try:
        WebhookNotificationRecoveryGuard(
            repository=FakeRepository(),
            worker=FakeWorker(),
            **case,
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {case}"
    )

print("[TEST] INVALID_CONFIG_REJECTED= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery guard"
)
