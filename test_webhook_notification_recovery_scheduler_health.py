
from datetime import datetime, timedelta

from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)
from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
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

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1

        if self.fail:
            raise RuntimeError("Simulated worker failure")

        return {
            "discovered": 0,
            "recovered_retry": 0,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }


def make_scheduler():
    repository = FakeRepository()
    worker = FakeWorker()

    guard = WebhookNotificationRecoveryGuard(
        repository=repository,
        worker=worker,
        enabled=True,
        dry_run=False,
        max_batch_size=10,
        retry_delay_seconds=60,
    )

    scheduler = WebhookNotificationRecoveryScheduler(
        worker=guard,
        limit=10,
        retry_delay_seconds=60,
    )

    return scheduler, repository, worker


now = datetime(2026, 10, 23, 14, 0, 0)


# 1. 初始健康状态
scheduler, repo, worker = make_scheduler()

result = scheduler.get_health(now=now)

assert result["status"] == "DEGRADED"
assert result["reason"] == "NO_SUCCESS_YET"

print("[TEST] INITIAL_DEGRADED= True")


# 2. 查询健康状态不执行 Worker
assert worker.calls == 0
assert repo.scan_calls == 0

print("[TEST] HEALTH_CHECK_READ_ONLY= True")


# 3. 最近成功，健康
scheduler.stats["last_success_time"] = (
    now - timedelta(seconds=30)
)
scheduler.stats["consecutive_failures"] = 0

result = scheduler.get_health(now=now)

assert result["status"] == "HEALTHY"

print("[TEST] HEALTHY_AFTER_SUCCESS= True")


# 4. 连续失败一次
scheduler.stats["consecutive_failures"] = 1

result = scheduler.get_health(now=now)

assert result["status"] == "DEGRADED"
assert result["reason"] == "RECENT_FAILURES"

print("[TEST] ONE_FAILURE_DEGRADED= True")


# 5. 连续失败三次
scheduler.stats["consecutive_failures"] = 3

result = scheduler.get_health(now=now)

assert result["status"] == "UNHEALTHY"
assert result["reason"] == "TOO_MANY_FAILURES"

print("[TEST] THREE_FAILURES_UNHEALTHY= True")


# 6. 恢复后正常
scheduler.stats["consecutive_failures"] = 0
scheduler.stats["last_success_time"] = now

result = scheduler.get_health(now=now)

assert result["status"] == "HEALTHY"

print("[TEST] RECOVERED_HEALTHY= True")


# 7. 最近成功时间过期
scheduler.stats["last_success_time"] = (
    now - timedelta(seconds=301)
)

result = scheduler.get_health(now=now)

assert result["status"] == "UNHEALTHY"
assert result["reason"] == "SUCCESS_TOO_OLD"

print("[TEST] STALE_SUCCESS_UNHEALTHY= True")


# 8. 返回运行统计
assert result["total_runs"] == 0
assert result["consecutive_failures"] == 0

print("[TEST] HEALTH_INCLUDES_STATS= True")


# 9. 健康查询不修改统计
before = scheduler.get_stats()

scheduler.get_health(now=now)

after = scheduler.get_stats()

assert before == after

print("[TEST] HEALTH_DOES_NOT_MUTATE_STATS= True")


# 10. 多次健康查询不执行 Worker
for _ in range(5):
    scheduler.get_health(now=now)

assert worker.calls == 0
assert repo.scan_calls == 0

print("[TEST] REPEATED_HEALTH_CHECK_READ_ONLY= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler health integration"
)
