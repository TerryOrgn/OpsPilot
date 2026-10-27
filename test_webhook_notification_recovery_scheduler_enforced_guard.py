
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
            {"ID": 101, "CLAIM_TOKEN": "token-101"},
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
            raise RuntimeError("Simulated worker failure")

        return {
            "discovered": 1,
            "recovered_retry": 1,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }


def make_guard(
    enabled=False,
    dry_run=True,
    fail=False,
):
    repo = FakeRepository()
    worker = FakeWorker(fail=fail)

    guard = WebhookNotificationRecoveryGuard(
        repository=repo,
        worker=worker,
        enabled=enabled,
        dry_run=dry_run,
        max_batch_size=10,
        retry_delay_seconds=60,
    )

    return guard, repo, worker


# 1. 默认安装 Guard
scheduler = WebhookNotificationRecoveryScheduler()

assert isinstance(
    scheduler.worker,
    WebhookNotificationRecoveryGuard,
)

print("[TEST] DEFAULT_GUARD_REQUIRED= True")


# 2. 拒绝直接注入 Worker
try:
    WebhookNotificationRecoveryScheduler(
        worker=FakeWorker()
    )
except TypeError:
    pass
else:
    raise AssertionError(
        "Direct Worker injection should be rejected"
    )

print("[TEST] DIRECT_WORKER_REJECTED= True")


# 3. 默认禁止恢复
scheduler = WebhookNotificationRecoveryScheduler()
result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert scheduler.get_stats()["executed_count"] == 0

print("[TEST] DEFAULT_DISABLED= True")


# 4. 禁用时不访问数据库
guard, repo, worker = make_guard()

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard
)

result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert repo.scan_calls == 0
assert worker.calls == 0

print("[TEST] DISABLED_NO_DB_ACCESS= True")


# 5. DRY_RUN 只读扫描
guard, repo, worker = make_guard(
    enabled=True,
    dry_run=True,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard
)

result = scheduler.run_once()

assert result["event_type"] == "DRY_RUN"
assert repo.scan_calls == 1
assert worker.calls == 0

print("[TEST] DRY_RUN_NO_RECOVERY= True")


# 6. 显式执行
guard, repo, worker = make_guard(
    enabled=True,
    dry_run=False,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard
)

result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"
assert worker.calls == 1
assert scheduler.get_stats()["executed_count"] == 1

print("[TEST] EXPLICIT_EXECUTION= True")


# 7. 执行结果统计
assert result["worker_stats"]["recovered_retry"] == 1
assert result["worker_stats"]["errors"] == 0

print("[TEST] EXECUTION_STATS= True")


# 8. Guard 内部异常
guard, repo, worker = make_guard(
    enabled=True,
    dry_run=False,
    fail=True,
)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=guard
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] GUARDED_FAILURE_RECORDED= True")


# 9. 不接受任意对象
try:
    WebhookNotificationRecoveryScheduler(
        worker=object()
    )
except TypeError:
    pass
else:
    raise AssertionError(
        "Unknown worker object should be rejected"
    )

print("[TEST] UNKNOWN_WORKER_REJECTED= True")


# 10. 非法参数仍然拒绝
try:
    WebhookNotificationRecoveryScheduler(
        interval_seconds=0
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid interval should be rejected"
    )

print("[TEST] INVALID_INTERVAL_REJECTED= True")


print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery scheduler enforced guard"
)
