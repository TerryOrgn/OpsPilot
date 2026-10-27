
import threading
import time

from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)


class FakeRecoveryWorker:

    def __init__(
        self,
        delay_seconds=0,
        fail=False,
        task_errors=0,
    ):
        self.delay_seconds = delay_seconds
        self.fail = fail
        self.task_errors = task_errors
        self.calls = 0
        self.started = threading.Event()

    def run_once(
        self,
        limit=100,
        retry_delay_seconds=60,
    ):
        self.calls += 1
        self.started.set()

        if self.delay_seconds:
            time.sleep(self.delay_seconds)

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


# 1. 正常执行
worker = FakeRecoveryWorker()

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
    interval_seconds=60,
)

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "SUCCESS"
assert stats["total_runs"] == 1
assert stats["success_count"] == 1
assert stats["failure_count"] == 0

print("[TEST] NORMAL_RUN_SUCCESS= True")


# 2. 成功时间正确记录
assert stats["last_run_time"] is not None
assert stats["last_success_time"] is not None
assert stats["consecutive_failures"] == 0

print("[TEST] SUCCESS_STATS_RECORDED= True")


# 3. 数据库扫描异常
worker = FakeRecoveryWorker(fail=True)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
)

result = scheduler.run_once()
stats = scheduler.get_stats()

assert result["event_type"] == "FAILED"
assert stats["failure_count"] == 1
assert stats["consecutive_failures"] == 1
assert stats["last_error_time"] is not None

print("[TEST] DATABASE_ERROR_RECORDED= True")


# 4. Worker 任务级异常
worker = FakeRecoveryWorker(task_errors=1)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
)

result = scheduler.run_once()

assert result["event_type"] == "FAILED"
assert scheduler.get_stats()["failure_count"] == 1

print("[TEST] TASK_ERROR_RECORDED= True")


# 5. 连续失败后恢复成功
worker = FakeRecoveryWorker(fail=True)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
)

scheduler.run_once()
scheduler.run_once()

assert scheduler.get_stats()["consecutive_failures"] == 2

worker.fail = False
scheduler.run_once()

stats = scheduler.get_stats()

assert stats["total_runs"] == 3
assert stats["failure_count"] == 2
assert stats["success_count"] == 1
assert stats["consecutive_failures"] == 0

print("[TEST] FAILURE_COUNTER_RESETS= True")


# 6. 防重入
worker = FakeRecoveryWorker(delay_seconds=0.3)

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
)

thread = threading.Thread(
    target=scheduler.run_once
)

thread.start()

assert worker.started.wait(timeout=2)

overlap_result = scheduler.run_once()

thread.join(timeout=3)

assert not thread.is_alive()
assert overlap_result["event_type"] == "SKIPPED_OVERLAP"
assert worker.calls == 1
assert scheduler.get_stats()["skipped_overlaps"] == 1

print("[TEST] OVERLAP_PREVENTED= True")


# 7. APScheduler 启动和停止
worker = FakeRecoveryWorker()

scheduler = WebhookNotificationRecoveryScheduler(
    worker=worker,
    interval_seconds=0.1,
)

try:
    scheduler.start()
    scheduler.start()

    time.sleep(0.35)

    assert worker.calls >= 1
    assert scheduler.scheduler.running

finally:
    scheduler.stop()

assert not scheduler.scheduler.running

print("[TEST] SCHEDULER_START_STOP= True")


# 8. 非法参数
for invalid in (0, -1, None, True):
    try:
        WebhookNotificationRecoveryScheduler(
            worker=FakeRecoveryWorker(),
            interval_seconds=invalid,
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_INTERVAL_REJECTED= True")


print("[INFO] SCHEDULER_STATS=", stats)

print(
    "[TEST] ALL PASS: "
    "Webhook notification recovery scheduler"
)
