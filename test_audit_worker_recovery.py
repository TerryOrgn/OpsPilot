
from audit_task_queue import BoundedAuditQueue
from audit_worker import AuditWorker


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class RecoveryRetryService:
    def __init__(self):
        self.calls = []

    def execute(self, audit):
        event_id = audit["event_id"]
        self.calls.append(event_id)

        if event_id == "EVT-FAIL":
            raise RuntimeError(
                "Simulated audit processing failure"
            )

        return {
            "status": "SUCCESS",
            "event_id": event_id,
            "attempts": 1,
        }


audit_queue = BoundedAuditQueue(maxsize=2)
retry_service = RecoveryRetryService()

first = audit_queue.submit({
    "event_id": "EVT-FAIL"
})

second = audit_queue.submit({
    "event_id": "EVT-SUCCESS"
})

check(
    "BOTH_EVENTS_QUEUED",
    first["status"] == "QUEUED"
    and second["status"] == "QUEUED",
)

worker = AuditWorker(
    audit_queue=audit_queue,
    retry_service=retry_service,
)

worker.start()

completed = audit_queue.wait_until_done(timeout=2)

check(
    "BOTH_TASKS_COMPLETED",
    completed,
)

check(
    "WORKER_STOPPED",
    worker.stop(timeout=2),
)

check(
    "BOTH_EVENTS_EXECUTED",
    retry_service.calls
    == ["EVT-FAIL", "EVT-SUCCESS"],
)

check(
    "TWO_RESULTS_RECORDED",
    len(worker.results) == 2,
)

check(
    "FIRST_EVENT_FAILED",
    worker.results[0]["status"] == "FAILED"
    and worker.results[0]["event_id"] == "EVT-FAIL",
)

check(
    "SECOND_EVENT_SUCCESS",
    worker.results[1]["status"] == "SUCCESS"
    and worker.results[1]["event_id"] == "EVT-SUCCESS",
)

check(
    "QUEUE_EMPTY",
    audit_queue.size() == 0,
)

print("[TEST] ALL PASS: Audit Worker Recovery")
