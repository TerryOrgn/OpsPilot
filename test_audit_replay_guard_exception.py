
import tempfile
from pathlib import Path

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class FailOnceRetryService:
    def __init__(self):
        self.calls = 0

    def execute(self, audit):
        self.calls += 1

        if self.calls == 1:
            raise ConnectionError("Simulated failure")

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

        retry = FailOnceRetryService()
        service = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        first = service.replay("EVT-001", approved=True)

        check("FIRST_REPLAY_FAILED", first["status"] == "FAILED")
        check(
            "FAILURE_TYPE_PRESERVED",
            first["last_error_type"] == "ConnectionError",
        )
        check("FIRST_EXECUTION_ATTEMPTED", retry.calls == 1)

        second = service.replay("EVT-001", approved=True)

        check(
            "REPLAY_ALLOWED_AFTER_EXCEPTION",
            second["status"] == "SUCCESS",
        )
        check("SECOND_EXECUTION_ATTEMPTED", retry.calls == 2)
        check(
            "EVENT_ID_PRESERVED",
            second["event_id"] == "EVT-001",
        )

    print("[TEST] ALL PASS: Replay Guard Exception Release")


if __name__ == "__main__":
    main()
