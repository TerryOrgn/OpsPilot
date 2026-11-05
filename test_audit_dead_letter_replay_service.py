
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
        path = Path(directory) / "dead_letters.jsonl"
        recorder = DeadLetterRecorder(path)

        for event_id, error_type in [
            ("EVT-001", "ConnectionError"),
            ("EVT-002", "ValueError"),
        ]:
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

        retry_service = FakeRetryService()

        operation_path = Path(directory) / "replay_operations.jsonl"

        service = DeadLetterReplayService(
            path,
            retry_service,
            operation_recorder=ReplayOperationRecorder(operation_path),
        )

        original_content = path.read_text(encoding="utf-8")

        result = service.replay("EVT-001")
        check("APPROVAL_REQUIRED", result["reason"] == "APPROVAL_REQUIRED")
        check("NO_EXECUTION_WITHOUT_APPROVAL", len(retry_service.calls) == 0)

        result = service.replay("EVT-UNKNOWN", approved=True)
        check("UNKNOWN_EVENT_REJECTED", result["reason"] == "EVENT_NOT_FOUND")

        result = service.replay("EVT-002", approved=True)
        check("INELIGIBLE_EVENT_REJECTED", result["reason"] == "NOT_ELIGIBLE")

        result = service.replay("EVT-001", approved=True)
        check("APPROVED_REPLAY_SUCCESS", result["status"] == "SUCCESS")
        check("ONLY_ONE_EXECUTION", len(retry_service.calls) == 1)
        check(
            "ORIGINAL_EVENT_ID_PRESERVED",
            retry_service.calls[0]["event_id"] == "EVT-001",
        )
        check("RETRY_RESULT_PRESERVED", result["attempts"] == 1)

        check(
            "DEAD_LETTER_FILE_UNCHANGED",
            path.read_text(encoding="utf-8") == original_content,
        )

        # 重复 Event ID 必须拒绝，不能任选其中一条执行。
        recorder.record(
            {"event_id": "EVT-001", "event": "JOB_MONITORING_SUMMARY"},
            {
                "status": "FAILED",
                "event_id": "EVT-001",
                "last_error_type": "ConnectionError",
            },
        )

        result = service.replay("EVT-001", approved=True)
        check("DUPLICATE_EVENT_REJECTED", result["reason"] == "DUPLICATE_EVENT_ID")
        check("NO_EXTRA_EXECUTION", len(retry_service.calls) == 1)

    print("[TEST] ALL PASS: Controlled Dead Letter Replay")


if __name__ == "__main__":
    main()
