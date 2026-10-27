
from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)
from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)


class FakeRepository:

    def __init__(self):
        self.scan_calls = 0

    def get_expired_lease_notifications(self, limit=100):
        self.scan_calls += 1

        return [
            {
                "ID": 101,
                "CLAIM_TOKEN": "token-101",
            },
            {
                "ID": 102,
                "CLAIM_TOKEN": None,
            },
        ][:limit]


class FakeWorker:

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1

        if self.fail:
            raise RuntimeError("Simulated recovery failure")

        return {
            "discovered": 2,
            "recovered_retry": 1,
            "recovered_dead": 0,
            "skipped": 1,
            "errors": 0,
        }


# 1. 默认 Scheduler 使用 Guard
scheduler = WebhookNotificationRecoveryScheduler()

assert isinstance(
    scheduler.worker,
    WebhookNotificationRecoveryGuard,
)

print("[TEST] DEFAULT_GUARD_INSTALLED= True")


# 2. 默认禁用，不执行恢复
result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert scheduler.get_stats()["disabled_count"] == 1
assert scheduler.get_stats()["executed_count"] == 0

print("[TEST] DEFAULT_SCHEDULER_DISABLED= True")


# 3. DISABLED 不扫描、不调用 Worker
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=False,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard,
)

result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert repo.scan_calls == 0
assert worker.calls == 0

print("[TEST] DISABLED_NO_DB_ACCESS= True")


# 4. DRY_RUN 只扫描
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=True,
    dry_run=True,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard,
)

result = scheduler.run_once()

assert result["event_type"] == "DRY_RUN"
assert repo.scan_calls == 1
assert worker.calls == 0

print("[TEST] SCHEDULER_DRY_RUN_READ_ONLY= True")


# 5. DRY_RUN 统计
stats = scheduler.get_stats()

assert stats["dry_run_count"] == 1
assert stats["executed_count"] == 0
assert stats["success_count"] == 1
assert result["worker_stats"]["missing_token"] == 1

print("[TEST] DRY_RUN_STATS_CORRECT= True")


# 6. 显式启用实际执行
repo = FakeRepository()
worker = FakeWorker()

guard = WebhookNotificationRecoveryGuard(
    repository=repo,
    worker=worker,
    enabled=True,
    dry_run=False,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard,
)

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "EXECUTED"
assert worker.calls == 1
assert stats["executed_count"] == 1
assert stats["disabled_count"] == 0

print("[TEST] SCHEDULER_EXECUTION_ALLOWED= True")


# 7. 执行统计正确传递
assert result["worker_stats"]["recovered_retry"] == 1
assert result["worker_stats"]["skipped"] == 1

print("[TEST] EXECUTION_STATS_PRESERVED= True")


# 8. Guard 执行失败时记录失败
worker = FakeWorker(fail=True)

guard = WebhookNotificationRecoveryGuard(
    repository=FakeRepository(),
    worker=worker,
    enabled=True,
    dry_run=False,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard,
)

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "FAILED"
assert stats["failure_count"] == 1
assert stats["executed_count"] == 0

print("[TEST] GUARD_ERROR_RECORDED= True")


# 9. 旧版 Fake Worker 兼容性
worker = FakeWorker()

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
)

result = scheduler.run_once()

assert result["event_type"] == "SUCCESS"
assert scheduler.get_stats()["success_count"] == 1

print("[TEST] LEGACY_WORKER_COMPATIBLE= True")


# 10. 禁用状态不等于实际恢复
scheduler = WebhookNotificationRecoveryScheduler()

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "DISABLED"
assert stats["success_count"] == 1
assert stats["executed_count"] == 0
assert stats["disabled_count"] == 1

print("[TEST] DISABLED_NOT_COUNTED_AS_EXECUTION= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery scheduler guard"
)
