
import threading
import time

from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)
from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)


class FakeRecoveryWorker:

    def __init__(
        self,
        fail=False,
        task_errors=0,
        delay=0,
    ):
        self.fail = fail
        self.task_errors = task_errors
        self.delay = delay
        self.calls = 0
        self.started = threading.Event()

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1
        self.started.set()

        if self.delay:
            time.sleep(self.delay)

        if self.fail:
            raise ConnectionError(
                "Simulated database connection failure"
            )

        return {
            "discovered": 2,
            "recovered_retry": 1,
            "recovered_dead": 1,
            "skipped": 0,
            "errors": self.task_errors,
        }


class FakeRepository:

    def get_expired_lease_notifications(self, limit=100):
        return []


def make_scheduler(
    worker=None,
    interval_seconds=60,
):
    if worker is None:
        worker = FakeRecoveryWorker()

    guard = WebhookNotificationRecoveryGuard(
        repository=FakeRepository(),
        worker=worker,
        enabled=True,
        dry_run=False,
        max_batch_size=10,
        retry_delay_seconds=60,
    )

    scheduler = WebhookNotificationRecoveryScheduler(
        worker=guard,
        interval_seconds=interval_seconds,
        limit=10,
        retry_delay_seconds=60,
    )

    return scheduler, worker


# --------------------------------------------------
# 1. 正常执行
# --------------------------------------------------

scheduler, worker = make_scheduler()

result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"
assert worker.calls == 1

print("[TEST] NORMAL_RUN_EXECUTED= True")


# --------------------------------------------------
# 2. 成功统计
# --------------------------------------------------

stats = scheduler.get_stats()

assert stats["total_runs"] == 1
assert stats["success_count"] == 1
assert stats["executed_count"] == 1
assert stats["failure_count"] == 0

print("[TEST] SUCCESS_STATS_RECORDED= True")


# --------------------------------------------------
# 3. 数据库异常
# --------------------------------------------------

scheduler, worker = make_scheduler(
    FakeRecoveryWorker(fail=True)
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] DATABASE_ERROR_RECORDED= True")


# --------------------------------------------------
# 4. Worker 任务级错误
# --------------------------------------------------

scheduler, worker = make_scheduler(
    FakeRecoveryWorker(task_errors=1)
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] TASK_ERROR_RECORDED= True")


# --------------------------------------------------
# 5. 连续失败后恢复
# --------------------------------------------------

worker = FakeRecoveryWorker(fail=True)
scheduler, worker = make_scheduler(worker)

scheduler.run_once()
scheduler.run_once()

assert (
    scheduler.get_stats()["consecutive_failures"] == 2
)

worker.fail = False

result = scheduler.run_once()

assert result["event_type"] == "EXECUTED"
assert (
    scheduler.get_stats()["consecutive_failures"] == 0
)

print("[TEST] FAILURE_COUNTER_RESETS= True")


# --------------------------------------------------
# 6. 防重入
# --------------------------------------------------

worker = FakeRecoveryWorker(delay=0.3)
scheduler, worker = make_scheduler(worker)

first_result = {}


def run_first():
    first_result["value"] = scheduler.run_once()


thread = threading.Thread(target=run_first)
thread.start()

assert worker.started.wait(timeout=2)

overlap_result = scheduler.run_once()

thread.join(timeout=3)

assert not thread.is_alive()
assert overlap_result["event_type"] == "SKIPPED_OVERLAP"
assert first_result["value"]["event_type"] == "EXECUTED"
assert worker.calls == 1
assert scheduler.get_stats()["skipped_overlaps"] == 1

print("[TEST] OVERLAP_PREVENTED= True")


# --------------------------------------------------
# 7. APScheduler 启动与停止
# --------------------------------------------------

scheduler, worker = make_scheduler(
    interval_seconds=0.1
)

try:
    scheduler.start()
    time.sleep(0.4)
finally:
    scheduler.stop()

assert worker.calls >= 1
assert scheduler.get_stats()["executed_count"] >= 1

print("[TEST] SCHEDULER_START_STOP= True")


# --------------------------------------------------
# 8. 非法间隔
# --------------------------------------------------

try:
    make_scheduler(interval_seconds=0)
except ValueError:
    pass
else:
    raise AssertionError(
        "Invalid interval should be rejected"
    )

print("[TEST] INVALID_INTERVAL_REJECTED= True")


print(
    "[TEST] ALL PASS: "
    "Recovery scheduler guarded regression"
)
