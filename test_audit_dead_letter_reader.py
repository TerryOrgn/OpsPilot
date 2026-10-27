
import json
import tempfile
from pathlib import Path

from audit_dead_letter_reader import DeadLetterReader
from audit_dead_letter_recorder import DeadLetterRecorder


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "dead_letters.jsonl"
        recorder = DeadLetterRecorder(path)

        for event_id in ("EVT-001", "EVT-002"):
            recorder.record(
                {"event_id": event_id, "event": "JOB_MONITORING_SUMMARY"},
                {
                    "status": "FAILED",
                    "event_id": event_id,
                    "last_error_type": "ConnectionError",
                },
            )

        records = DeadLetterReader(path).read_all()

        check("TWO_RECORDS_READ", len(records) == 2)
        check(
            "ORDER_PRESERVED",
            [r["event_id"] for r in records] == ["EVT-001", "EVT-002"],
        )
        check(
            "AUDIT_IDS_MATCH",
            all(r["audit"]["event_id"] == r["event_id"] for r in records),
        )
        check(
            "FAILURE_IDS_MATCH",
            all(r["failure"]["event_id"] == r["event_id"] for r in records),
        )
        check(
            "FAILURE_STATUS_VALID",
            all(r["failure"]["status"] == "FAILED" for r in records),
        )

        original_content = path.read_text(encoding="utf-8")
        DeadLetterReader(path).read_all()
        check(
            "FILE_UNCHANGED",
            path.read_text(encoding="utf-8") == original_content,
        )

        try:
            DeadLetterReader(Path(directory) / "missing.jsonl").read_all()
        except FileNotFoundError:
            check("MISSING_FILE_REJECTED", True)
        else:
            raise AssertionError("MISSING_FILE_REJECTED")

        path.write_text('{"invalid": ', encoding="utf-8")
        try:
            DeadLetterReader(path).read_all()
        except ValueError as exc:
            check("INVALID_JSON_REJECTED", "line 1" in str(exc))
        else:
            raise AssertionError("INVALID_JSON_REJECTED")

        invalid_record = {
            "event_id": "EVT-001",
            "audit": {"event_id": "EVT-OTHER"},
            "failure": {"event_id": "EVT-001", "status": "FAILED"},
        }
        path.write_text(json.dumps(invalid_record) + "\n", encoding="utf-8")

        try:
            DeadLetterReader(path).read_all()
        except ValueError as exc:
            check("MISMATCHED_ID_REJECTED", "line 1" in str(exc))
        else:
            raise AssertionError("MISMATCHED_ID_REJECTED")

        invalid_record["audit"]["event_id"] = "EVT-001"
        invalid_record["failure"]["status"] = "SUCCESS"
        path.write_text(json.dumps(invalid_record) + "\n", encoding="utf-8")

        try:
            DeadLetterReader(path).read_all()
        except ValueError as exc:
            check("INVALID_STATUS_REJECTED", "line 1" in str(exc))
        else:
            raise AssertionError("INVALID_STATUS_REJECTED")

    print("[TEST] ALL PASS: Dead Letter Reader")


if __name__ == "__main__":
    main()
