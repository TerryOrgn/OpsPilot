
import time
from threading import Lock

from webhook_notification_outbox_scheduler import (
    WebhookNotificationOutboxScheduler,
)


class FakeWorker:

    def __init__(self):
        self.lock = Lock()
        self.call_count = 0
        self.active_count = 0
        self.max_active_count = 0

    def run_once(self, limit=10):
        with self.lock:
            self.call_count += 1
            self.active_count += 1

            self.max_active_count = max(
                self.max_active_count,
                self.active_count,
            )

            current_call = self.call_count

        try:
            # 故意超过调度间隔，测试防重入
            time.sleep(3)

            return {
                "discovered": 0,
                "claimed": 0,
                "sent": 0,
                "retry": 0,
                "dead": 0,
                "skipped": 0,
                "call": current_call,
            }

        finally:
            with self.lock:
                self.active_count -= 1


worker = FakeWorker()

scheduler = WebhookNotificationOutboxScheduler(
    worker=worker,
    interval_seconds=2,
)


# 1. 参数校验
for invalid in (0, -1, None, "2", True):
    try:
        WebhookNotificationOutboxScheduler(
            interval_seconds=invalid
        )
    except ValueError:
        continue

    raise AssertionError(
        f"Expected ValueError: {invalid!r}"
    )

print("[TEST] INVALID_INTERVAL_REJECTED= True")


# 2. 启动调度器
scheduler.start()

assert scheduler.scheduler.running

print("[TEST] SCHEDULER_STARTED= True")


# 3. 重复启动不创建新调度任务
scheduler.start()

assert len(
    scheduler.scheduler.get_jobs()
) == 1

print("[TEST] DUPLICATE_START_IGNORED= True")


# 4. 等待至少一次调度
try:
    time.sleep(7.5)

finally:
    scheduler.shutdown()


# 5. 已停止
assert not scheduler.scheduler.running

print("[TEST] SCHEDULER_STOPPED= True")


# 6. 实际执行过
assert worker.call_count >= 1

print("[TEST] WORKER_EXECUTED= True")


# 7. 没有并发重入
assert worker.max_active_count == 1

print("[TEST] NO_CONCURRENT_REENTRY= True")


# 8. 执行统计正确
stats = scheduler.stats

assert stats["total_runs"] == worker.call_count
assert stats["success_count"] == worker.call_count
assert stats["failure_count"] == 0
assert stats["last_success_time"] is not None

print("[TEST] SCHEDULER_STATS_CORRECT= True")


print("[INFO] WORKER_CALL_COUNT=", worker.call_count)
print("[INFO] MAX_ACTIVE_COUNT=", worker.max_active_count)
print("[INFO] SCHEDULER_STATS=", stats)


print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox scheduler"
)
