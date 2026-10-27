
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

    def run_once(self, limit=100, retry_delay_seconds=60):
        self.calls += 1
        return {
            "discovered": 0,
            "recovered_retry": 0,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }


def make_scheduler(enabled, dry_run):
    repo = FakeRepository()
    worker = FakeWorker()

    guard = WebhookNotificationRecoveryGuard(
        repository=repo,
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

    return scheduler, repo, worker


# --------------------------------------------------
# 1. DISABLED 模式
# --------------------------------------------------

disabled_scheduler, disabled_repo, disabled_worker = (
    make_scheduler(enabled=False, dry_run=True)
)

disabled_result = disabled_scheduler.run_once()
disabled_stats = disabled_scheduler.get_stats()
disabled_health = disabled_scheduler.get_health()

assert disabled_result["event_type"] == "DISABLED"
print("[TEST] DISABLED_EVENT= True")

assert disabled_worker.calls == 0
assert disabled_repo.scan_calls == 0
print("[TEST] DISABLED_NO_EXECUTION= True")

assert disabled_stats["disabled_count"] == 1
assert disabled_stats["executed_count"] == 0
print("[TEST] DISABLED_STATS= True")

print("[OBSERVE] DISABLED_HEALTH=", disabled_health)


# --------------------------------------------------
# 2. DRY_RUN 模式
# --------------------------------------------------

dry_scheduler, dry_repo, dry_worker = (
    make_scheduler(enabled=True, dry_run=True)
)

dry_result = dry_scheduler.run_once()
dry_stats = dry_scheduler.get_stats()
dry_health = dry_scheduler.get_health()

assert dry_result["event_type"] == "DRY_RUN"
print("[TEST] DRY_RUN_EVENT= True")

assert dry_worker.calls == 0
assert dry_repo.scan_calls == 1
print("[TEST] DRY_RUN_NO_RECOVERY= True")

assert dry_stats["dry_run_count"] == 1
assert dry_stats["executed_count"] == 0
print("[TEST] DRY_RUN_STATS= True")

print("[OBSERVE] DRY_RUN_HEALTH=", dry_health)


# --------------------------------------------------
# 3. EXECUTED 模式
# --------------------------------------------------

active_scheduler, active_repo, active_worker = (
    make_scheduler(enabled=True, dry_run=False)
)

active_result = active_scheduler.run_once()
active_stats = active_scheduler.get_stats()
active_health = active_scheduler.get_health()

assert active_result["event_type"] == "EXECUTED"
print("[TEST] EXECUTED_EVENT= True")

assert active_worker.calls == 1
print("[TEST] EXECUTED_WORKER_CALLED= True")

assert active_stats["executed_count"] == 1
print("[TEST] EXECUTED_STATS= True")

print("[OBSERVE] EXECUTED_HEALTH=", active_health)


# --------------------------------------------------
# 4. 检查假健康风险
# --------------------------------------------------

assert disabled_health["status"] == "HEALTHY"
print("[TEST] DISABLED_FALSE_HEALTHY_OBSERVED= True")

assert dry_health["status"] == "HEALTHY"
print("[TEST] DRY_RUN_FALSE_HEALTHY_OBSERVED= True")

assert active_health["status"] == "HEALTHY"
print("[TEST] EXECUTED_HEALTHY= True")


print(
    "[TEST] ALL PASS: "
    "Recovery false healthy characterization"
)
