
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_task_queue import BoundedAuditQueue
from audit_retry_service import AuditRetryService
from audit_worker import AuditWorker
from audit_dead_letter_recorder import DeadLetterRecorder


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class SelectiveRecorder:
    def record(self, audit):
        if audit["event_id"] == "EVT-FAIL":
            raise ConnectionError("Database unavailable")
        return True


class BrokenDeadLetterRecorder:
    def record(self, audit, result):
        raise OSError("Disk unavailable")


def run_worker(events, dead_letter_recorder):
    queue = BoundedAuditQueue(maxsize=10)

    for event_id in events:
        queue.submit({"event_id": event_id})

    retry_service = AuditRetryService(
        recorder=SelectiveRecorder(),
        max_attempts=2,
        sleep_fn=lambda seconds: None,
    )

    worker = AuditWorker(
        audit_queue=queue,
        retry_service=retry_service,
        dead_letter_recorder=dead_letter_recorder,
    )

    worker.start()

    try:
        completed = queue.wait_until_done(timeout=3)
    finally:
        stopped = worker.stop(timeout=3)

    return worker, queue, completed, stopped


with TemporaryDirectory() as temp_dir:
    file_path = Path(temp_dir) / "dead_letters.jsonl"
    dlq = DeadLetterRecorder(file_path)

    # 场景一：一条失败，一条成功
    worker, queue, completed, stopped = run_worker(
        ["EVT-FAIL", "EVT-SUCCESS"],
        dlq,
    )

    check("TASKS_COMPLETED", completed)
    check("WORKER_STOPPED", stopped)

    check(
        "FAILED_EVENT_RECORDED",
        worker.results[0]["status"] == "FAILED"
        and worker.results[0]["dead_letter_status"]
        == "RECORDED",
    )

    check(
        "SUCCESS_EVENT_NOT_DEAD_LETTERED",
        worker.results[1]["status"] == "SUCCESS",
    )

    lines = file_path.read_text(
        encoding="utf-8"
    ).splitlines()

    check("ONLY_ONE_DEAD_LETTER", len(lines) == 1)

    entry = json.loads(lines[0])

    check(
        "EVENT_ID_PRESERVED",
        entry["event_id"] == "EVT-FAIL",
    )

    check(
        "FAILURE_DETAILS_PRESERVED",
        entry["failure"]["attempts"] == 2
        and entry["failure"]["last_error_type"]
        == "ConnectionError",
    )

    check("QUEUE_EMPTY", queue.size() == 0)

    # 场景二：死信保存失败
    worker2, queue2, completed2, stopped2 = run_worker(
        ["EVT-FAIL", "EVT-SUCCESS"],
        BrokenDeadLetterRecorder(),
    )

    check(
        "TASKS_COMPLETED_WHEN_DLQ_BROKEN",
        completed2,
    )

    check(
        "DLQ_FAILURE_RECORDED",
        worker2.results[0]["dead_letter_status"]
        == "FAILED"
        and worker2.results[0][
            "dead_letter_error_type"
        ] == "OSError",
    )

    check(
        "NEXT_EVENT_STILL_PROCESSED",
        worker2.results[1]["status"] == "SUCCESS",
    )

    check(
        "WORKER_STOPPED_AFTER_DLQ_FAILURE",
        stopped2,
    )

print("[TEST] ALL PASS: Audit Worker Dead Letter")
