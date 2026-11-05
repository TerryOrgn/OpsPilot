
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
        self.calls = 0

    def execute(self, audit):
        self.calls += 1
        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


class BrokenOperationRecorder:
    def record(self, operation):
        raise OSError("Audit storage unavailable")


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

        # Scenario 1: No recorder, no execution.
        retry = FakeRetryService()
        service = DeadLetterReplayService(dead_letter_path, retry)

        result = service.replay("EVT-001", approved=True)

        check("MISSING_RECORDER_REJECTED", result["status"] == "REJECTED")
        check(
            "MISSING_RECORDER_REASON",
            result["reason"] == "AUDIT_RECORDER_REQUIRED",
        )
        check("NO_EXECUTION_WITHOUT_RECORDER", retry.calls == 0)

        # Scenario 2: Unauthorized request remains rejected.
        result = service.replay("EVT-001", approved=False)
        check("UNAUTHORIZED_REJECTED", result["status"] == "REJECTED")
        check("UNAUTHORIZED_NOT_EXECUTED", retry.calls == 0)

        # Scenario 3: Recorder configured, replay succeeds.
        operation_recorder = ReplayOperationRecorder(operation_path)
        safe_retry = FakeRetryService()
        safe_service = DeadLetterReplayService(
            dead_letter_path,
            safe_retry,
            operation_recorder=operation_recorder,
        )

        result = safe_service.replay(
            "EVT-001",
            approved=True,
            actor="operator-A",
        )

        check("AUTHORIZED_SUCCESS", result["status"] == "SUCCESS")
        check("AUTHORIZED_EXECUTED_ONCE", safe_retry.calls == 1)

        entries = [
            json.loads(line)
            for line in operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        check(
            "STARTED_BEFORE_SUCCESS",
            [entry["status"] for entry in entries]
            == ["STARTED", "SUCCESS"],
        )

        # Scenario 4: Audit write failure blocks execution.
        broken_retry = FakeRetryService()
        broken_service = DeadLetterReplayService(
            dead_letter_path,
            broken_retry,
            operation_recorder=BrokenOperationRecorder(),
        )

        try:
            broken_service.replay("EVT-001", approved=True)
        except OSError:
            check("AUDIT_WRITE_FAILURE_PROPAGATED", True)
        else:
            raise AssertionError("AUDIT_WRITE_FAILURE_PROPAGATED")

        check("AUDIT_FAILURE_BLOCKS_EXECUTION", broken_retry.calls == 0)

    print("[TEST] ALL PASS: Mandatory Replay Audit")


if __name__ == "__main__":
    main()
