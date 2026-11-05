
import json
import tempfile
from pathlib import Path

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class FakeRetryService:
    def __init__(self):
        self.calls = []

    def execute(self, audit):
        self.calls.append(dict(audit))
        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


class FailingRetryService:
    def execute(self, audit):
        raise ConnectionError("Simulated retry failure")


def read_operations(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        dead_path = directory / "dead_letters.jsonl"
        operation_path = directory / "operations.jsonl"

        DeadLetterRecorder(dead_path).record(
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

        retry = FakeRetryService()
        service = DeadLetterReplayService(
            dead_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        # First approved replay.
        first = service.replay(
            "EVT-001", approved=True, actor="operator-A"
        )

        check("FIRST_REPLAY_SUCCESS", first["status"] == "SUCCESS")

        # Second approved replay of the same Event ID.
        second = service.replay(
            "EVT-001", approved=True, actor="operator-A"
        )

        check("SECOND_REPLAY_SUCCESS", second["status"] == "SUCCESS")
        check("TWO_EXECUTIONS", len(retry.calls) == 2)

        entries = read_operations(operation_path)

        check("FOUR_AUDIT_ENTRIES", len(entries) == 4)

        check(
            "AUDIT_ORDER",
            [entry["status"] for entry in entries]
            == ["STARTED", "SUCCESS", "STARTED", "SUCCESS"],
        )

        first_started, first_success, second_started, second_success = entries

        first_id = first_started.get("replay_attempt_id")
        second_id = second_started.get("replay_attempt_id")

        check(
            "FIRST_ATTEMPT_ID_PRESENT",
            isinstance(first_id, str) and bool(first_id),
        )

        check(
            "SECOND_ATTEMPT_ID_PRESENT",
            isinstance(second_id, str) and bool(second_id),
        )

        check(
            "FIRST_ATTEMPT_MATCHES",
            first_id == first_success.get("replay_attempt_id"),
        )

        check(
            "SECOND_ATTEMPT_MATCHES",
            second_id == second_success.get("replay_attempt_id"),
        )

        check(
            "DIFFERENT_ATTEMPT_IDS",
            first_id != second_id,
        )

        # Exception path must preserve the Attempt ID.
        failing_service = DeadLetterReplayService(
            dead_path,
            FailingRetryService(),
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        failed = failing_service.replay(
            "EVT-001", approved=True, actor="operator-A"
        )

        check("EXCEPTION_REPLAY_FAILED", failed["status"] == "FAILED")

        entries = read_operations(operation_path)

        check("SIX_AUDIT_ENTRIES", len(entries) == 6)

        failed_started, failed_terminal = entries[-2:]

        check(
            "EXCEPTION_AUDIT_ORDER",
            [failed_started["status"], failed_terminal["status"]]
            == ["STARTED", "FAILED"],
        )

        check(
            "EXCEPTION_ATTEMPT_MATCHES",
            bool(failed_started.get("replay_attempt_id"))
            and failed_started.get("replay_attempt_id")
            == failed_terminal.get("replay_attempt_id"),
        )

        check(
            "EXCEPTION_ATTEMPT_UNIQUE",
            failed_started["replay_attempt_id"]
            not in {first_id, second_id},
        )

    print("[TEST] ALL PASS: Replay Attempt ID")


if __name__ == "__main__":
    main()
