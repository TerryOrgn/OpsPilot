
from audit_task_queue import BoundedAuditQueue
from audit_queue_adapter import AuditQueueAdapter
from audit_retry_service import AuditRetryService
from audit_worker import AuditWorker
from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


class FakeLLM:
    def decide(self, message):
        return {
            "type": "TOOL_CALL",
            "tool_name": "get_recent_abnormal_jobs",
            "arguments": '{"limit": 10}',
        }


class FakeRepository:
    def get_recent_jobs(self):
        return []


class FakeScheduler:
    pass


class AlwaysFailRecorder:
    def __init__(self):
        self.calls = []

    def record(self, audit):
        self.calls.append(audit["event_id"])
        raise ConnectionError(
            "Simulated database unavailable"
        )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


audit_queue = BoundedAuditQueue(maxsize=2)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=AuditQueueAdapter(audit_queue),
)

# 先不启动 Worker，确定性地填满队列
responses = [
    agent.ask("查询最近异常 JOB")
    for _ in range(3)
]

check(
    "BUSINESS_UNAFFECTED",
    all(r["ok"] is True for r in responses),
)

check(
    "FIRST_TWO_QUEUED",
    all(
        r["audit_recording_status"] == "QUEUED"
        for r in responses[:2]
    ),
)

check(
    "THIRD_REJECTED",
    responses[2]["audit_recording_status"]
    == "REJECTED",
)

check(
    "QUEUE_CAPACITY_ENFORCED",
    audit_queue.size() == 2,
)

event_ids = [
    r["audit"]["event_id"]
    for r in responses[:2]
]

check(
    "EVENT_IDS_UNIQUE",
    len(set(event_ids)) == 2,
)

# 启动 Worker，模拟数据库持续不可用
recorder = AlwaysFailRecorder()

retry_service = AuditRetryService(
    recorder=recorder,
    max_attempts=2,
    sleep_fn=lambda seconds: None,
)

worker = AuditWorker(
    audit_queue=audit_queue,
    retry_service=retry_service,
)

worker.start()

try:
    completed = audit_queue.wait_until_done(timeout=3)

    check(
        "ALL_ACCEPTED_TASKS_COMPLETED",
        completed,
    )

    check(
        "QUEUE_DRAINED",
        audit_queue.size() == 0,
    )

    check(
        "TWO_FAILURE_RESULTS",
        len(worker.results) == 2
        and all(
            result["status"] == "FAILED"
            for result in worker.results
        ),
    )

    check(
        "RETRY_LIMIT_ENFORCED",
        len(recorder.calls) == 4,
    )

    check(
        "EVENT_IDS_PRESERVED",
        recorder.calls
        == [
            event_ids[0],
            event_ids[0],
            event_ids[1],
            event_ids[1],
        ],
    )

    check(
        "FAILURE_DIAGNOSTICS",
        all(
            result["last_error_type"]
            == "ConnectionError"
            and result["attempts"] == 2
            for result in worker.results
        ),
    )

finally:
    stopped = worker.stop(timeout=3)

check(
    "WORKER_STOPPED",
    stopped,
)

print("[TEST] ALL PASS: Audit Backpressure")
