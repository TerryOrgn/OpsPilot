
import tempfile
from pathlib import Path
from threading import Event, Thread

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder


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
            raise TimeoutError("Test execution timed out")

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

        retry = BlockingRetryService()
        service = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        first_result = {}

        def run_first_replay():
            first_result["value"] = service.replay(
                "EVT-001",
                approved=True,
                actor="operator-A",
            )

        worker = Thread(target=run_first_replay)
        worker.start()

        try:
            check(
                "FIRST_REPLAY_STARTED",
                retry.started.wait(timeout=3),
            )

            second_result = service.replay(
                "EVT-001",
                approved=True,
                actor="operator-B",
            )

            check(
                "SECOND_REPLAY_REJECTED",
                second_result["status"] == "REJECTED",
            )
            check(
                "CONCURRENT_REJECTION_REASON",
                second_result["reason"]
                == "REPLAY_ALREADY_IN_PROGRESS",
            )
            check(
                "ONLY_ONE_EXECUTION_DURING_RACE",
                retry.calls == 1,
            )

        finally:
            retry.release.set()
            worker.join(timeout=3)

        check("WORKER_FINISHED", not worker.is_alive())
        check(
            "FIRST_REPLAY_SUCCESS",
            first_result["value"]["status"] == "SUCCESS",
        )
        check(
            "EXECUTION_COUNT_UNCHANGED",
            retry.calls == 1,
        )

        # A later replay is allowed after the first completes.
        third_result = service.replay(
            "EVT-001",
            approved=True,
            actor="operator-C",
        )

        check(
            "REPLAY_ALLOWED_AFTER_RELEASE",
            third_result["status"] == "SUCCESS",
        )
        check(
            "SECOND_SEQUENTIAL_EXECUTION",
            retry.calls == 2,
        )

    print("[TEST] ALL PASS: ReplayService Concurrency")


if __name__ == "__main__":
    main()
