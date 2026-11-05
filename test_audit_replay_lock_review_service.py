
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_lock_review_service import ReplayLockReviewService


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def write_audit(recorder, event_id, attempt_id, status):
    recorder.record({
        "action": "DEAD_LETTER_REPLAY",
        "event_id": event_id,
        "actor": "operator-A",
        "replay_attempt_id": attempt_id,
        "status": status,
    })


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)

        db_path = directory / "guard.db"
        operation_path = directory / "operations.jsonl"

        guard = ReplayProcessGuard(db_path)
        recorder = ReplayOperationRecorder(operation_path)

        # Historical successful replay.
        write_audit(recorder, "EVT-001", "ATTEMPT-OLD", "STARTED")
        write_audit(recorder, "EVT-001", "ATTEMPT-OLD", "SUCCESS")

        # Current attempt holds the lock but has not finished.
        token = guard.try_acquire(
            "EVT-001",
            replay_attempt_id="ATTEMPT-CURRENT",
        )

        check("CURRENT_LOCK_ACQUIRED", bool(token))

        write_audit(
            recorder,
            "EVT-001",
            "ATTEMPT-CURRENT",
            "STARTED",
        )

        service = ReplayLockReviewService(
            db_path,
            operation_path,
            stale_after_seconds=1800,
        )

        results = service.review()

        check("ONE_LOCK_REVIEWED", len(results) == 1)

        item = results[0]

        check(
            "CURRENT_ATTEMPT_SELECTED",
            item["replay_attempt_id"] == "ATTEMPT-CURRENT",
        )
        check(
            "HISTORICAL_SUCCESS_NOT_USED",
            item["audit_status"] == "ATTEMPT_INCOMPLETE",
        )
        check(
            "MANUAL_REVIEW_REQUIRED",
            item["recommendation"] == "MANUAL_REVIEW_REQUIRED",
        )

        # Review must not mutate or release the lock.
        check(
            "LOCK_REMAINS_HELD",
            guard.try_acquire(
                "EVT-001",
                replay_attempt_id="ATTEMPT-OTHER",
            ) is None,
        )

        # Append terminal audit to the current attempt.
        write_audit(
            recorder,
            "EVT-001",
            "ATTEMPT-CURRENT",
            "FAILED",
        )

        results = service.review()

        check(
            "CURRENT_FAILURE_DETECTED",
            results[0]["audit_status"] == "ATTEMPT_FAILED",
        )
        check(
            "FAILED_ATTEMPT_NOT_AUTO_RELEASED",
            guard.try_acquire("EVT-001") is None,
        )

        check(
            "OWNER_CAN_RELEASE",
            guard.release("EVT-001", token),
        )

        check(
            "NO_LOCKS_AFTER_RELEASE",
            service.review() == [],
        )

    print("[TEST] ALL PASS: Replay Lock Review Service")


if __name__ == "__main__":
    main()
