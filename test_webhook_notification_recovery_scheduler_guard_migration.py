
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
            {"ID": 102, "CLAIM_TOKEN": None},
        ][:limit]


class FakeWorker:

    def __init__(self, fail=False, task_errors=0):
        self.calls = 0
        self.fail = fail
        self.task_errors = task_errors

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1

        if self.fail:
            raise RuntimeError(
                "Simulated recovery failure"
            )

        return {
            "discovered": 2,
            "recovered_retry": 1,
            "recovered_dead": 0,
            "skipped": 1,
            "errors": self.task_errors,
        }


def make_scheduler(
    enabled=False,
    dry_run=True,
    fail=False,
    task_errors=0,
):
    repo = FakeRepository()

    worker = FakeWorker(
        fail=fail,
        task_errors=task_errors,
    )

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
# 1. 默认 Guard
# --------------------------------------------------

scheduler = WebhookNotificationRecoveryScheduler()

assert isinstance(
    scheduler.worker,
    WebhookNotificationRecoveryGuard,
)

print("[TEST] DEFAULT_GUARD_INSTALLED= True")


# --------------------------------------------------
# 2. 直接注入 Worker 被拒绝
# --------------------------------------------------

try:
    WebhookNotificationRecoveryScheduler(
        worker=FakeWorker()
    )
except TypeError:
    pass
else:
    raise AssertionError(
        "Direct Worker injection must be rejected"
    )

print("[TEST] DIRECT_WORKER_REJECTED= True")


# --------------------------------------------------
# 3. 默认禁用
# --------------------------------------------------

scheduler = WebhookNotificationRecoveryScheduler()
result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert scheduler.get_stats()["disabled_count"] == 1

print("[TEST] DEFAULT_DISABLED= True")


# --------------------------------------------------
# 4. 禁用时不访问数据库
# --------------------------------------------------

scheduler, repo, worker = make_scheduler()

result = scheduler.run_once()

assert result["event_type"] == "DISABLED"
assert repo.scan_calls == 0
assert worker.calls == 0

print("[TEST] DISABLED_NO_DB_ACCESS= True")


# --------------------------------------------------
# 5. DRY_RUN 只读
# --------------------------------------------------

scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=True,
)

result = scheduler.run_once()

assert result["event_type"] == "DRY_RUN"
assert repo.scan_calls == 1
assert worker.calls == 0

print("[TEST] DRY_RUN_READ_ONLY= True")


# --------------------------------------------------
# 6. DRY_RUN 统计
# --------------------------------------------------

stats = scheduler.get_stats()

assert stats["dry_run_count"] == 1
assert stats["executed_count"] == 0
assert result["worker_stats"]["missing_token"] == 1

print("[TEST] DRY_RUN_STATS_CORRECT= True")


# --------------------------------------------------
# 7. 显式授权执行
# --------------------------------------------------

scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=False,
)

result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"
assert worker.calls == 1
assert scheduler.get_stats()["executed_count"] == 1

print("[TEST] EXPLICIT_EXECUTION_ALLOWED= True")


# --------------------------------------------------
# 8. 执行统计保留
# --------------------------------------------------

assert result["worker_stats"]["recovered_retry"] == 1
assert result["worker_stats"]["skipped"] == 1

print("[TEST] EXECUTION_STATS_PRESERVED= True")


# --------------------------------------------------
# 9. Worker 异常
# --------------------------------------------------

scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=False,
    fail=True,
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] WORKER_ERROR_RECORDED= True")


# --------------------------------------------------
# 10. 任务级错误
# --------------------------------------------------

scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=False,
    task_errors=1,
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] TASK_ERROR_RECORDED= True")


# --------------------------------------------------
# 11. 禁用不计为实际执行
# --------------------------------------------------

scheduler, repo, worker = make_scheduler()

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "DISABLED"
assert stats["success_count"] == 1
assert stats["executed_count"] == 0
assert stats["disabled_count"] == 1

print("[TEST] DISABLED_NOT_EXECUTED= True")


# --------------------------------------------------
# 12. DRY_RUN 不计为实际执行
# --------------------------------------------------

scheduler, repo, worker = make_scheduler(
    enabled=True,
    dry_run=True,
)

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "DRY_RUN"
assert stats["dry_run_count"] == 1
assert stats["executed_count"] == 0

print("[TEST] DRY_RUN_NOT_EXECUTED= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler guard migration"
)
