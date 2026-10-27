
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
        self.fail = True

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1

        if self.fail:
            raise ConnectionError(
                "Simulated database connection failure"
            )

        return {
            "discovered": 0,
            "recovered_retry": 0,
            "recovered_dead": 0,
            "skipped": 0,
            "errors": 0,
        }


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


def assert_health(expected_status, expected_reason):
    result = scheduler.get_health()

    assert result["status"] == expected_status, result
    assert result["reason"] == expected_reason, result

    print(
        f"[HEALTH] status={result['status']} "
        f"reason={result['reason']} "
        f"failures={result['consecutive_failures']}"
    )


# --------------------------------------------------
# 1. 初始状态
# --------------------------------------------------

assert_health("DEGRADED", "NO_SUCCESS_YET")

print("[TEST] INITIAL_DEGRADED= True")


# --------------------------------------------------
# 2. 第一次失败
# --------------------------------------------------

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert_health("DEGRADED", "NO_SUCCESS_YET")

assert scheduler.get_stats()["consecutive_failures"] == 1

print("[TEST] FIRST_FAILURE_DEGRADED= True")


# --------------------------------------------------
# 3. 第二次失败
# --------------------------------------------------

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert_health("DEGRADED", "NO_SUCCESS_YET")

assert scheduler.get_stats()["consecutive_failures"] == 2

print("[TEST] SECOND_FAILURE_DEGRADED= True")


# --------------------------------------------------
# 4. 第三次失败
# --------------------------------------------------

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert_health("UNHEALTHY", "TOO_MANY_FAILURES")

assert scheduler.get_stats()["consecutive_failures"] == 3

print("[TEST] THIRD_FAILURE_UNHEALTHY= True")


# --------------------------------------------------
# 5. 恢复 Worker
# --------------------------------------------------

worker.fail = False

result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"

assert_health("HEALTHY", "RUNNING_NORMALLY")

print("[TEST] RECOVERY_HEALTHY= True")


# --------------------------------------------------
# 6. 失败计数重置
# --------------------------------------------------

stats = scheduler.get_stats()

assert stats["consecutive_failures"] == 0
assert stats["failure_count"] == 3
assert stats["success_count"] == 1

print("[TEST] FAILURE_COUNTER_RESET= True")


# --------------------------------------------------
# 7. Guard 执行统计
# --------------------------------------------------

assert stats["executed_count"] == 1
assert stats["disabled_count"] == 0
assert stats["dry_run_count"] == 0

print("[TEST] GUARDED_EXECUTION_COUNT= True")


# --------------------------------------------------
# 8. Worker 调用次数
# --------------------------------------------------

assert worker.calls == 4
assert repository.scan_calls == 0

print("[TEST] WORKER_CALL_COUNT= True")


# --------------------------------------------------
# 9. 健康查询不产生额外调用
# --------------------------------------------------

before_calls = worker.calls
before_stats = scheduler.get_stats()

for _ in range(5):
    scheduler.get_health()

assert worker.calls == before_calls
assert scheduler.get_stats() == before_stats

print("[TEST] HEALTH_QUERY_READ_ONLY= True")


# --------------------------------------------------
# 10. 最终健康状态
# --------------------------------------------------

health = scheduler.get_health()

assert health["status"] == "HEALTHY"
assert health["consecutive_failures"] == 0
assert health["total_runs"] == 4

print("[TEST] FINAL_HEALTHY= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler health transition"
)
