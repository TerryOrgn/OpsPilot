
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
        return []


class FakeWorker:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def run_once(self, limit=100, retry_delay_seconds=60):
        self.calls += 1

        if self.fail:
            raise RuntimeError("Simulated recovery failure")

        return {
            "discovered": 0,
            "recovered_retry": 0,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }


def make_scheduler(enabled, dry_run):
    repository = FakeRepository()
    worker = FakeWorker()

    guard = WebhookNotificationRecoveryGuard(
        repository=repository,
        worker=worker,
        enabled=enabled,
        dry_run=dry_run,
        max_batch_size=10,
        retry_delay_seconds=60,
    )

    scheduler = WebhookNotificationRecoveryScheduler(
        worker=guard,
        limit=10,
        retry_delay_seconds=60,
    )

    return scheduler, repository, worker


# 1. 初始状态
scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=False,
)

assert scheduler.get_health()["recovery_status"] == "NOT_RUN"
print("[TEST] INITIAL_NOT_RUN= True")


# 2. DISABLED 模式
disabled_scheduler, disabled_repo, disabled_worker = (
    make_scheduler(enabled=False, dry_run=True)
)

disabled_result = disabled_scheduler.run_once()
disabled_health = disabled_scheduler.get_health()

assert disabled_result["event_type"] == "DISABLED"
assert disabled_health["recovery_status"] == "DISABLED"
print("[TEST] DISABLED_STATUS= True")


# 3. DISABLED 不执行 Worker
assert disabled_worker.calls == 0
assert disabled_repo.scan_calls == 0
print("[TEST] DISABLED_NO_WORKER= True")


# 4. DRY_RUN 模式
dry_scheduler, dry_repo, dry_worker = make_scheduler(
    enabled=True,
    dry_run=True,
)

dry_result = dry_scheduler.run_once()
dry_health = dry_scheduler.get_health()

assert dry_result["event_type"] == "DRY_RUN"
assert dry_health["recovery_status"] == "DRY_RUN"
print("[TEST] DRY_RUN_STATUS= True")


# 5. DRY_RUN 只扫描
assert dry_worker.calls == 0
assert dry_repo.scan_calls == 1
print("[TEST] DRY_RUN_READ_ONLY= True")


# 6. EXECUTED 模式
active_result = scheduler.run_once()
active_health = scheduler.get_health()

assert active_result["event_type"] == "EXECUTED"
assert active_health["recovery_status"] == "EXECUTED"
print("[TEST] EXECUTED_STATUS= True")


# 7. EXECUTED 调用 Worker
assert worker.calls == 1
print("[TEST] EXECUTED_WORKER_CALLED= True")


# 8. 模拟执行失败
worker.fail = True

failed_result = scheduler.run_once()
failed_health = scheduler.get_health()

assert failed_result["event_type"] == "FAILED"
assert failed_health["recovery_status"] == "FAILED"
print("[TEST] FAILED_STATUS= True")


# 9. 失败后恢复
worker.fail = False

recovered_result = scheduler.run_once()
recovered_health = scheduler.get_health()

assert recovered_result["event_type"] == "EXECUTED"
assert recovered_health["recovery_status"] == "EXECUTED"
assert recovered_health["status"] == "HEALTHY"
print("[TEST] FAILED_TO_EXECUTED= True")


# 10. 健康查询不执行 Worker
before_calls = worker.calls
before_stats = scheduler.get_stats()

for _ in range(5):
    scheduler.get_health()

assert worker.calls == before_calls
assert scheduler.get_stats() == before_stats

print("[TEST] HEALTH_READ_ONLY= True")


# 11. 调度健康与 Recovery 状态独立
assert disabled_health["status"] == "HEALTHY"
assert disabled_health["recovery_status"] == "DISABLED"

assert dry_health["status"] == "HEALTHY"
assert dry_health["recovery_status"] == "DRY_RUN"

print("[TEST] HEALTH_AND_RECOVERY_SEPARATED= True")


# 12. 最终统计
stats = scheduler.get_stats()

assert stats["total_runs"] == 3
assert stats["success_count"] == 2
assert stats["failure_count"] == 1
assert stats["consecutive_failures"] == 0

print("[TEST] FINAL_STATS= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler execution status"
)
