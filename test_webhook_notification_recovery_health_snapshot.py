
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


def make_scheduler(enabled=True, dry_run=False):
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


# 1. 初始状态：允许执行，但尚未成功运行
scheduler, repo, worker = make_scheduler()

snapshot = scheduler.get_health_snapshot()

assert snapshot["scheduler_health"] == "DEGRADED"
assert snapshot["recovery_status"] == "NOT_RUN"
assert snapshot["ready_for_recovery"] is True
assert snapshot["readiness_reason"] == "READY"

print("[TEST] INITIAL_READY_NOT_RUN= True")


# 2. 健康快照只读
assert worker.calls == 0
assert repo.scan_calls == 0

print("[TEST] INITIAL_SNAPSHOT_READ_ONLY= True")


# 3. DISABLED
disabled_scheduler, disabled_repo, disabled_worker = (
    make_scheduler(enabled=False, dry_run=True)
)

disabled_scheduler.run_once()
disabled_snapshot = (
    disabled_scheduler.get_health_snapshot()
)

assert disabled_snapshot["scheduler_health"] == "HEALTHY"
assert disabled_snapshot["recovery_status"] == "DISABLED"
assert disabled_snapshot["ready_for_recovery"] is False
assert disabled_snapshot["readiness_reason"] == "GUARD_DISABLED"

print("[TEST] DISABLED_NOT_READY= True")


# 4. DRY_RUN
dry_scheduler, dry_repo, dry_worker = make_scheduler(
    enabled=True,
    dry_run=True,
)

dry_scheduler.run_once()
dry_snapshot = dry_scheduler.get_health_snapshot()

assert dry_snapshot["scheduler_health"] == "HEALTHY"
assert dry_snapshot["recovery_status"] == "DRY_RUN"
assert dry_snapshot["ready_for_recovery"] is False
assert dry_snapshot["readiness_reason"] == "DRY_RUN_ENABLED"

print("[TEST] DRY_RUN_NOT_READY= True")


# 5. EXECUTED
result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"

snapshot = scheduler.get_health_snapshot()

assert snapshot["scheduler_health"] == "HEALTHY"
assert snapshot["recovery_status"] == "EXECUTED"
assert snapshot["ready_for_recovery"] is True

print("[TEST] EXECUTED_READY= True")


# 6. 连续失败三次
worker.fail = True

for _ in range(3):
    result = scheduler.run_once()
    assert result["event_type"] == "FAILED"

snapshot = scheduler.get_health_snapshot()

assert snapshot["scheduler_health"] == "UNHEALTHY"
assert snapshot["recovery_status"] == "FAILED"
assert snapshot["ready_for_recovery"] is False
assert snapshot["readiness_reason"] == "SCHEDULER_UNHEALTHY"

print("[TEST] UNHEALTHY_NOT_READY= True")


# 7. 故障恢复
worker.fail = False

result = scheduler.run_once()
assert result["event_type"] == "EXECUTED"

snapshot = scheduler.get_health_snapshot()

assert snapshot["scheduler_health"] == "HEALTHY"
assert snapshot["recovery_status"] == "EXECUTED"
assert snapshot["ready_for_recovery"] is True
assert snapshot["readiness_reason"] == "READY"

print("[TEST] RECOVERED_READY= True")


# 8. 包含统计信息
assert snapshot["total_runs"] == 5
assert snapshot["consecutive_failures"] == 0
assert snapshot["last_success_time"] is not None

print("[TEST] SNAPSHOT_INCLUDES_STATS= True")


# 9. 多次读取不触发 Worker
before_calls = worker.calls
before_stats = scheduler.get_stats()

for _ in range(5):
    scheduler.get_health_snapshot()

assert worker.calls == before_calls
assert scheduler.get_stats() == before_stats

print("[TEST] REPEATED_SNAPSHOT_READ_ONLY= True")


# 10. 快照字段完整性
expected_keys = {
    "scheduler_health",
    "health_reason",
    "recovery_status",
    "ready_for_recovery",
    "readiness_reason",
    "total_runs",
    "consecutive_failures",
    "last_success_time",
}

assert set(snapshot.keys()) == expected_keys

print("[TEST] SNAPSHOT_SCHEMA_VALID= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler health snapshot"
)
