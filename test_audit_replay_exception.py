
import json
import tempfile
from pathlib import Path

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class FakeFailingRetryService:
    def __init__(self):
        self.calls = 0

    def execute(self, audit):
        self.calls += 1
        raise RuntimeError("Simulated replay failure")


def main():
    with tempfile.TemporaryDirectory() as directory:
        dead_letter_path = Path(directory) / "dead_letters.jsonl"
        operation_path = Path(directory) / "replay_operations.jsonl"

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

        retry = FakeFailingRetryService()
        service = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        original_dead_letter = dead_letter_path.read_text(
            encoding="utf-8"
        )

        result = service.replay(
            "EVT-001",
            approved=True,
            actor="operator-A",
        )

        check("FAILED_RESULT", result["status"] == "FAILED")
        check("EVENT_ID_PRESERVED", result["event_id"] == "EVT-001")
        check(
            "EXCEPTION_TYPE_PRESERVED",
            result["last_error_type"] == "RuntimeError",
        )
        check(
            "EXCEPTION_REASON_RECORDED",
            result["reason"] == "REPLAY_EXECUTION_EXCEPTION",
        )
        check("EXECUTION_ATTEMPTED_ONCE", retry.calls == 1)

        entries = [
            json.loads(line)
            for line in operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        check("TWO_OPERATIONS_RECORDED", len(entries) == 2)

        check(
            "AUDIT_ORDER",
            [entry["status"] for entry in entries] == ["STARTED", "FAILED"],
        )
        check(
            "FAILED_OPERATION_AUDITED",
            entries[1]["status"] == "FAILED",
        )
        check(
            "ERROR_TYPE_AUDITED",
            entries[1]["last_error_type"] == "RuntimeError",
        )
        check(
            "ACTOR_AUDITED",
            entries[1]["actor"] == "operator-A",
        )
        check(
            "TIMESTAMP_RECORDED",
            bool(entries[1]["timestamp"]),
        )
        check(
            "DEAD_LETTER_UNCHANGED",
            dead_letter_path.read_text(encoding="utf-8")
            == original_dead_letter,
        )

    print("[TEST] ALL PASS: Replay Exception Audit")


if __name__ == "__main__":
    main()
