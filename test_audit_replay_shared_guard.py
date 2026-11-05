
import tempfile
from pathlib import Path
from threading import Event, Thread

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_guard import ReplayConcurrencyGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class BlockingRetryService:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def execute(self, audit):
        self.calls += 1
        self.started.set()

        if not self.release.wait(timeout=5):
            raise TimeoutError("Test timed out")

        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        dead_letter_path = directory / "dead_letters.jsonl"
        operation_path = directory / "operations.jsonl"

        DeadLetterRecorder(dead_letter_path).record(
            {
                "event_id": "EVT-001",
                "event": "JOB_MONITORING_SUMMARY",
            },
            {
                "status": "FAILED",
                "event_id": "EVT-001",
                "last_error_type": "ConnectionError",
            },
        )

        guard = ReplayConcurrencyGuard()
        retry = BlockingRetryService()
        recorder = ReplayOperationRecorder(operation_path)

        service_a = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=recorder,
            concurrency_guard=guard,
        )

        service_b = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=recorder,
            concurrency_guard=guard,
        )

        first_result = {}

        def run_first():
            first_result["value"] = service_a.replay(
                "EVT-001",
                approved=True,
                actor="operator-A",
            )

        worker = Thread(target=run_first)
        worker.start()

        try:
            check("FIRST_INSTANCE_STARTED", retry.started.wait(3))

            second = service_b.replay(
                "EVT-001",
                approved=True,
                actor="operator-B",
            )

            check("SECOND_INSTANCE_REJECTED", second["status"] == "REJECTED")
            check(
                "SHARED_GUARD_REJECTION_REASON",
                second["reason"] == "REPLAY_ALREADY_IN_PROGRESS",
            )
            check("ONLY_ONE_EXECUTION", retry.calls == 1)

        finally:
            retry.release.set()
            worker.join(timeout=3)

        check("FIRST_WORKER_FINISHED", not worker.is_alive())
        check(
            "FIRST_INSTANCE_SUCCESS",
            first_result["value"]["status"] == "SUCCESS",
        )

        third = service_b.replay(
            "EVT-001",
            approved=True,
            actor="operator-B",
        )

        check("SECOND_INSTANCE_ALLOWED_LATER", third["status"] == "SUCCESS")
        check("TOTAL_EXECUTIONS_TWO", retry.calls == 2)

    print("[TEST] ALL PASS: Shared Replay Guard")


if __name__ == "__main__":
    main()
