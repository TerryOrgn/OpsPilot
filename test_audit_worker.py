
from threading import Event, current_thread

from audit_task_queue import BoundedAuditQueue
from audit_worker import AuditWorker


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def make_audit(event_id):
    return {
        "event_id": event_id,
        "event": "JOB_MONITORING_SUMMARY",
        "tool_name": "get_recent_abnormal_jobs",
        "total_abnormal_count": 0,
        "returned_count": 0,
        "truncated": False,
        "summary_status": "SUCCESS",
    }


class FakeRetryService:
    def __init__(self, should_raise=False):
        self.should_raise = should_raise
        self.calls = []
        self.thread_names = []
        self.called_event = Event()

    def execute(self, audit):
        self.calls.append(dict(audit))
        self.thread_names.append(
            current_thread().name
        )
        self.called_event.set()

        if self.should_raise:
            raise RuntimeError(
                "Simulated worker processing failure"
            )

        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


# 场景一：后台正常处理
audit_queue = BoundedAuditQueue(maxsize=2)
retry_service = FakeRetryService()

audit_queue.submit(make_audit("EVT-WORKER-001"))

worker = AuditWorker(
    audit_queue=audit_queue,
    retry_service=retry_service,
)

worker.start()

check(
    "BACKGROUND_EXECUTED",
    retry_service.called_event.wait(timeout=2),
)

check(
    "BACKGROUND_THREAD",
    retry_service.thread_names
    == ["OpsPilotAuditWorker"],
)

check(
    "BACKGROUND_TASK_COMPLETED",
    audit_queue.wait_until_done(timeout=2),
)

check(
    "BACKGROUND_TASK_COMPLETED",
    audit_queue.wait_until_done(timeout=2),
)

check(
    "WORKER_STOPPED",
    worker.stop(timeout=2),
)

check(
    "SUCCESS_RESULT",
    len(worker.results) == 1
    and worker.results[0]["status"] == "SUCCESS",
)

check(
    "QUEUE_EMPTY",
    audit_queue.size() == 0,
)


# 场景二：后台处理异常不会杀死 Worker
audit_queue = BoundedAuditQueue(maxsize=2)
retry_service = FakeRetryService(
    should_raise=True
)

audit_queue.submit(make_audit("EVT-WORKER-002"))

worker = AuditWorker(
    audit_queue=audit_queue,
    retry_service=retry_service,
)

worker.start()

check(
    "FAILED_EVENT_PROCESSED",
    retry_service.called_event.wait(timeout=2),
)

check(
    "FAILED_TASK_COMPLETED",
    audit_queue.wait_until_done(timeout=2),
)

check(
    "WORKER_STOPPED_AFTER_FAILURE",
    worker.stop(timeout=2),
)

check(
    "FAILED_RESULT_RECORDED",
    len(worker.results) == 1
    and worker.results[0]["status"] == "FAILED",
)

check(
    "ERROR_TYPE_RECORDED",
    worker.results[0]["last_error_type"]
    == "RuntimeError",
)

check(
    "FAILED_TASK_REMOVED_FROM_QUEUE",
    audit_queue.size() == 0,
)

print("[TEST] ALL PASS: Audit Worker")
