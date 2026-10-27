
import time
from threading import Event, Lock

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


class BlockingRecorder:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.completed = Event()
        self.calls = []
        self._lock = Lock()

    def record(self, audit):
        with self._lock:
            self.calls.append(dict(audit))

        self.started.set()

        # 模拟数据库持续阻塞
        if not self.release.wait(timeout=5):
            raise ConnectionError(
                "Simulated database timeout"
            )

        self.completed.set()
        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


audit_queue = BoundedAuditQueue(maxsize=2)
recorder = BlockingRecorder()

retry_service = AuditRetryService(
    recorder=recorder,
    max_attempts=2,
    sleep_fn=lambda seconds: None,
)

worker = AuditWorker(
    audit_queue=audit_queue,
    retry_service=retry_service,
)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=AuditQueueAdapter(audit_queue),
)

worker.start()

try:
    # 第一次调用：提交审计事件
    start = time.monotonic()

    response = agent.ask("查询最近异常 JOB")

    elapsed = time.monotonic() - start

    check(
        "AGENT_BUSINESS_SUCCESS",
        response["ok"] is True,
    )

    check(
        "AUDIT_QUEUED",
        response["audit_recording_status"] == "QUEUED",
    )

    check(
        "AGENT_FAST_RETURN",
        elapsed < 1.0,
    )

    check(
        "WORKER_STARTED_PROCESSING",
        recorder.started.wait(timeout=2),
    )

    check(
        "DATABASE_STILL_BLOCKED",
        not recorder.completed.is_set(),
    )

    check(
        "SUMMARY_AVAILABLE",
        isinstance(response["summary"], str)
        and bool(response["summary"]),
    )

    event_id = response["audit"]["event_id"]

    check(
        "EVENT_ID_GENERATED",
        isinstance(event_id, str)
        and bool(event_id),
    )

    # 模拟数据库恢复
    recorder.release.set()

    check(
        "BACKGROUND_TASK_COMPLETED",
        audit_queue.wait_until_done(timeout=3),
    )

    check(
        "DATABASE_WRITE_COMPLETED",
        recorder.completed.is_set(),
    )

    check(
        "EVENT_ID_CONSISTENT",
        len(recorder.calls) == 1
        and recorder.calls[0]["event_id"] == event_id,
    )

    check(
        "WORKER_SUCCESS_RESULT",
        len(worker.results) == 1
        and worker.results[0]["status"] == "SUCCESS",
    )

finally:
    # 即使断言失败，也释放阻塞中的 Worker
    recorder.release.set()
    stopped = worker.stop(timeout=3)

check(
    "WORKER_STOPPED",
    stopped,
)

print(
    "[TEST] ALL PASS: Agent Async Audit End-to-End"
)
