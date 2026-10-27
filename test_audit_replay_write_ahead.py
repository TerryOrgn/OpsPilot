
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
    def __init__(self, operation_path):
        self.operation_path = operation_path
        self.calls = 0
        self.started_seen = False

    def execute(self, audit):
        self.calls += 1
        entries = [
            json.loads(line)
            for line in self.operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        self.started_seen = (
            len(entries) == 1
            and entries[0]["status"] == "STARTED"
            and entries[0]["event_id"] == audit["event_id"]
        )

        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


class BrokenOperationRecorder:
    def record(self, operation):
        raise OSError("Audit disk unavailable")


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

        retry = FakeRetryService(operation_path)
        service = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        result = service.replay(
            "EVT-001",
            approved=True,
            actor="operator-A",
        )

        check("REPLAY_SUCCESS", result["status"] == "SUCCESS")
        check("STARTED_VISIBLE_BEFORE_EXECUTION", retry.started_seen)
        check("EXECUTED_ONCE", retry.calls == 1)

        entries = [
            json.loads(line)
            for line in operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        check("TWO_AUDIT_ENTRIES", len(entries) == 2)
        check(
            "AUDIT_ORDER",
            [e["status"] for e in entries] == ["STARTED", "SUCCESS"],
        )
        check(
            "EVENT_ID_PRESERVED",
            all(e["event_id"] == "EVT-001" for e in entries),
        )
        check(
            "ACTOR_PRESERVED",
            all(e["actor"] == "operator-A" for e in entries),
        )
        check(
            "TIMESTAMPS_PRESENT",
            all(bool(e.get("timestamp")) for e in entries),
        )

        blocked_retry = FakeRetryService(operation_path)
        blocked_service = DeadLetterReplayService(
            dead_letter_path,
            blocked_retry,
            operation_recorder=BrokenOperationRecorder(),
        )

        try:
            blocked_service.replay(
                "EVT-001",
                approved=True,
                actor="operator-A",
            )
        except OSError:
            check("AUDIT_WRITE_FAILURE_PROPAGATED", True)
        else:
            raise AssertionError("AUDIT_WRITE_FAILURE_PROPAGATED")

        check(
            "NO_EXECUTION_WHEN_AUDIT_FAILS",
            blocked_retry.calls == 0,
        )

        check(
            "NO_EXTRA_AUDIT_ENTRIES",
            len(operation_path.read_text(
                encoding="utf-8"
            ).splitlines()) == 2,
        )

    print("[TEST] ALL PASS: Replay Write-Ahead Audit")


if __name__ == "__main__":
    main()
