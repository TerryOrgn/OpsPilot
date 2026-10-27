
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


def main():
    with tempfile.TemporaryDirectory() as directory:
        dead_letter_path = Path(directory) / "dead_letters.jsonl"
        operation_path = Path(directory) / "replay_operations.jsonl"

        DeadLetterRecorder(dead_letter_path).record(
            {"event_id": "EVT-001", "event": "JOB_MONITORING_SUMMARY"},
            {
                "status": "FAILED",
                "event_id": "EVT-001",
                "last_error_type": "ConnectionError",
            },
        )

        retry = FakeRetryService()
        service = DeadLetterReplayService(
            dead_letter_path,
            retry,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        rejected = service.replay(
            "EVT-001", approved=False, actor="operator-A"
        )
        check("REJECTED_RESULT", rejected["status"] == "REJECTED")
        check("NO_REPLAY_WITHOUT_APPROVAL", len(retry.calls) == 0)

        succeeded = service.replay(
            "EVT-001", approved=True, actor="operator-A"
        )
        check("SUCCESS_RESULT", succeeded["status"] == "SUCCESS")
        check("ONE_REPLAY_EXECUTED", len(retry.calls) == 1)

        entries = [
            json.loads(line)
            for line in operation_path.read_text(encoding="utf-8").splitlines()
        ]

        check("THREE_OPERATIONS_RECORDED", len(entries) == 3)

        check(
            "AUDIT_ORDER",
            [entry["status"] for entry in entries]
            == ["REJECTED", "STARTED", "SUCCESS"],
        )
        check(
            "ACTION_RECORDED",
            all(e["action"] == "DEAD_LETTER_REPLAY" for e in entries),
        )
        check(
            "ACTOR_RECORDED",
            all(e["actor"] == "operator-A" for e in entries),
        )
        check(
            "EVENT_ID_PRESERVED",
            all(e["event_id"] == "EVT-001" for e in entries),
        )
        check("REJECTION_AUDITED", entries[0]["status"] == "REJECTED")
        check("SUCCESS_AUDITED", entries[2]["status"] == "SUCCESS")
        check("ATTEMPTS_RECORDED", entries[2]["attempts"] == 1)
        check(
            "TIMESTAMP_RECORDED",
            all(bool(e.get("timestamp")) for e in entries),
        )

    print("[TEST] ALL PASS: Replay Operation Audit")


if __name__ == "__main__":
    main()
