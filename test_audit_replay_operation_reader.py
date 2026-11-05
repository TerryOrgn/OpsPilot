
import json
import tempfile
from pathlib import Path

from audit_replay_operation_reader import ReplayOperationReader
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_attempt_matcher import ReplayAttemptMatcher


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def rejects(path):
    try:
        ReplayOperationReader(path).read_all()
    except (ValueError, FileNotFoundError):
        return True
    return False


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        path = directory / "operations.jsonl"

        recorder = ReplayOperationRecorder(path)

        recorder.record({
            "action": "DEAD_LETTER_REPLAY",
            "event_id": "EVT-001",
            "actor": "operator-A",
            "status": "STARTED",
            "replay_attempt_id": "ATTEMPT-A",
        })

        recorder.record({
            "action": "DEAD_LETTER_REPLAY",
            "event_id": "EVT-001",
            "actor": "operator-A",
            "status": "SUCCESS",
            "replay_attempt_id": "ATTEMPT-A",
        })

        recorder.record({
            "action": "DEAD_LETTER_REPLAY",
            "event_id": "EVT-001",
            "actor": "operator-B",
            "status": "STARTED",
            "replay_attempt_id": "ATTEMPT-B",
        })

        records = ReplayOperationReader(path).read_all()

        check("THREE_RECORDS_READ", len(records) == 3)
        check(
            "ORDER_PRESERVED",
            [r["status"] for r in records]
            == ["STARTED", "SUCCESS", "STARTED"],
        )
        check(
            "TIMESTAMPS_PRESENT",
            all(bool(r.get("timestamp")) for r in records),
        )

        result = ReplayAttemptMatcher.match(
            {
                "event_id": "EVT-001",
                "replay_attempt_id": "ATTEMPT-B",
            },
            records,
        )

        check(
            "REAL_JSONL_MATCHES_CURRENT_ATTEMPT",
            result["status"] == "ATTEMPT_INCOMPLETE",
        )
        check(
            "HISTORICAL_SUCCESS_IGNORED",
            len(result["records"]) == 1,
        )

        missing = directory / "missing.jsonl"
        check("MISSING_FILE_REJECTED", rejects(missing))

        invalid_json = directory / "invalid.jsonl"
        invalid_json.write_text('{"broken":\n', encoding="utf-8")
        check("INVALID_JSON_REJECTED", rejects(invalid_json))

        invalid_action = directory / "invalid_action.jsonl"
        invalid_action.write_text(
            json.dumps({
                "action": "UNKNOWN",
                "event_id": "EVT-001",
                "status": "STARTED",
            }) + "\n",
            encoding="utf-8",
        )
        check("INVALID_ACTION_REJECTED", rejects(invalid_action))

        invalid_attempt = directory / "invalid_attempt.jsonl"
        invalid_attempt.write_text(
            json.dumps({
                "action": "DEAD_LETTER_REPLAY",
                "event_id": "EVT-001",
                "status": "STARTED",
                "replay_attempt_id": "",
            }) + "\n",
            encoding="utf-8",
        )
        check(
            "INVALID_ATTEMPT_REJECTED",
            rejects(invalid_attempt),
        )

        empty_line = directory / "empty_line.jsonl"
        empty_line.write_text("\n", encoding="utf-8")
        check("EMPTY_LINE_REJECTED", rejects(empty_line))

    print("[TEST] ALL PASS: Replay Operation Reader")


if __name__ == "__main__":
    main()
