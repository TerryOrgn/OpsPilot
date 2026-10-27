
import tempfile
from pathlib import Path

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_preview import DeadLetterReplayPreview


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "dead_letters.jsonl"
        recorder = DeadLetterRecorder(path)

        cases = [
            ("EVT-001", "ConnectionError"),
            ("EVT-002", "ValueError"),
            ("EVT-003", None),
        ]

        for event_id, error_type in cases:
            recorder.record(
                {
                    "event_id": event_id,
                    "event": "JOB_MONITORING_SUMMARY",
                },
                {
                    "status": "FAILED",
                    "event_id": event_id,
                    "last_error_type": error_type,
                },
            )

        original_content = path.read_text(encoding="utf-8")

        preview = DeadLetterReplayPreview(path).build()

        check("THREE_EVENTS", len(preview) == 3)

        check(
            "ORDER_PRESERVED",
            [item["event_id"] for item in preview]
            == ["EVT-001", "EVT-002", "EVT-003"],
        )

        check(
            "CONNECTION_ERROR_ELIGIBLE",
            preview[0]["replay_eligible"] is True,
        )

        check(
            "VALUE_ERROR_REQUIRES_REVIEW",
            preview[1]["replay_eligible"] is False,
        )

        check(
            "UNKNOWN_ERROR_REQUIRES_REVIEW",
            preview[2]["replay_eligible"] is False,
        )

        check(
            "RETRYABLE_REASON",
            preview[0]["reason"] == "RETRYABLE_FAILURE",
        )

        check(
            "MANUAL_REVIEW_REASON",
            all(
                item["reason"] == "MANUAL_REVIEW_REQUIRED"
                for item in preview[1:]
            ),
        )

        check(
            "FAILURE_TYPES_PRESERVED",
            [item["failure_type"] for item in preview]
            == ["ConnectionError", "ValueError", None],
        )

        check(
            "SOURCE_FILE_UNCHANGED",
            path.read_text(encoding="utf-8") == original_content,
        )

        check(
            "NO_AUDIT_PAYLOAD_IN_PREVIEW",
            all("audit" not in item for item in preview),
        )

    print("[TEST] ALL PASS: Dead Letter Replay Preview")


if __name__ == "__main__":
    main()
