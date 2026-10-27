
import json

from webhook_notification_recovery_guard import (
    WebhookNotificationRecoveryGuard,
)
from webhook_notification_recovery_scheduler import (
    WebhookNotificationRecoveryScheduler,
)
from webhook_notification_recovery_health_serializer import (
    WebhookNotificationRecoveryHealthSerializer,
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

serializer = WebhookNotificationRecoveryHealthSerializer()


def get_json_snapshot():
    snapshot = scheduler.get_health_snapshot()
    serialized = serializer.serialize(snapshot)

    # 验证真正的 JSON 编码与解码
    encoded = json.dumps(serialized)
    decoded = json.loads(encoded)

    assert decoded == serialized

    return decoded


# 1. 初始状态
data = get_json_snapshot()

assert data["scheduler_health"] == "DEGRADED"
assert data["recovery_status"] == "NOT_RUN"
assert data["ready_for_recovery"] is True
assert data["last_success_time"] is None

print("[TEST] INITIAL_JSON_SNAPSHOT= True")


# 2. 初始快照不执行 Worker
assert worker.calls == 0
assert repository.scan_calls == 0

print("[TEST] INITIAL_READ_ONLY= True")


# 3. 正常执行
result = scheduler.run_once()
assert result["event_type"] == "EXECUTED"

data = get_json_snapshot()

assert data["scheduler_health"] == "HEALTHY"
assert data["recovery_status"] == "EXECUTED"
assert data["ready_for_recovery"] is True

print("[TEST] EXECUTED_JSON_SNAPSHOT= True")


# 4. 时间已经转换为字符串
assert isinstance(data["last_success_time"], str)
assert "T" in data["last_success_time"]

print("[TEST] TIMESTAMP_SERIALIZED= True")


# 5. 第一次执行失败
worker.fail = True

result = scheduler.run_once()
assert result["event_type"] == "FAILED"

data = get_json_snapshot()

assert data["scheduler_health"] == "DEGRADED"
assert data["recovery_status"] == "FAILED"
assert data["consecutive_failures"] == 1

print("[TEST] FIRST_FAILURE_JSON= True")


# 6. 连续失败三次
for _ in range(2):
    result = scheduler.run_once()
    assert result["event_type"] == "FAILED"

data = get_json_snapshot()

assert data["scheduler_health"] == "UNHEALTHY"
assert data["recovery_status"] == "FAILED"
assert data["ready_for_recovery"] is False
assert data["readiness_reason"] == "SCHEDULER_UNHEALTHY"

print("[TEST] UNHEALTHY_JSON_SNAPSHOT= True")


# 7. 故障恢复
worker.fail = False

result = scheduler.run_once()
assert result["event_type"] == "EXECUTED"

data = get_json_snapshot()

assert data["scheduler_health"] == "HEALTHY"
assert data["recovery_status"] == "EXECUTED"
assert data["ready_for_recovery"] is True
assert data["consecutive_failures"] == 0

print("[TEST] RECOVERED_JSON_SNAPSHOT= True")


# 8. 统计信息一致
stats = scheduler.get_stats()

assert stats["total_runs"] == 5
assert stats["success_count"] == 2
assert stats["failure_count"] == 3
assert stats["consecutive_failures"] == 0

print("[TEST] SCHEDULER_STATS_CONSISTENT= True")


# 9. 快照查询不修改运行状态
before_calls = worker.calls
before_stats = scheduler.get_stats()

for _ in range(5):
    get_json_snapshot()

assert worker.calls == before_calls
assert scheduler.get_stats() == before_stats

print("[TEST] JSON_SNAPSHOT_READ_ONLY= True")


# 10. 输出完整 JSON
data = get_json_snapshot()

print(
    "[INFO] FINAL_JSON=",
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ),
)

assert data["total_runs"] == 5
assert data["ready_for_recovery"] is True

print("[TEST] FINAL_JSON_VALID= True")


print(
    "[TEST] ALL PASS: "
    "Recovery health JSON integration"
)
