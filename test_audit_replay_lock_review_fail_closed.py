
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_lock_review_service import ReplayLockReviewService


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db_path = root / "guard.db"
        audit_path = root / "operations.jsonl"

        guard = ReplayProcessGuard(db_path)
        token = guard.try_acquire(
            "EVT-CRASH",
            replay_attempt_id="ATTEMPT-CRASH",
        )
        check("LOCK_ACQUIRED", bool(token))

        recorder = ReplayOperationRecorder(audit_path)

        # A historical attempt exists, but the current one
        # crashed before its STARTED audit was written.
        recorder.record({
            "action": "DEAD_LETTER_REPLAY",
            "event_id": "EVT-CRASH",
            "actor": "operator-A",
            "status": "SUCCESS",
            "replay_attempt_id": "ATTEMPT-OLD",
        })

        service = ReplayLockReviewService(
            db_path, audit_path
        )

        results = service.review()
        check("ONE_LOCK_FOUND", len(results) == 1)

        item = results[0]
        check(
            "CURRENT_ATTEMPT_PRESERVED",
            item["replay_attempt_id"] == "ATTEMPT-CRASH",
        )
        check(
            "MISSING_STARTED_UNCERTAIN",
            item["audit_status"] == "CORRELATION_UNCERTAIN",
        )
        check(
            "MISSING_AUDIT_REASON",
            item["audit_reason"] == "ATTEMPT_AUDIT_NOT_FOUND",
        )
        check(
            "MANUAL_REVIEW_REQUIRED",
            item["recommendation"] == "MANUAL_REVIEW_REQUIRED",
        )
        check(
            "LOCK_STILL_HELD",
            guard.try_acquire("EVT-CRASH") is None,
        )

        # Corrupt the audit file deliberately.
        audit_path.write_text(
            '{"invalid":\n', encoding="utf-8"
        )

        rejected = False
        try:
            service.review()
        except ValueError:
            rejected = True

        check("CORRUPTED_AUDIT_REJECTED", rejected)
        check(
            "LOCK_PRESERVED_AFTER_READ_ERROR",
            guard.try_acquire("EVT-CRASH") is None,
        )

        # Only the original owner may release the lock.
        check(
            "OWNER_RELEASES_LOCK",
            guard.release("EVT-CRASH", token) is True,
        )

    print("[TEST] ALL PASS: Replay Lock Review Fail Closed")


if __name__ == "__main__":
    main()
