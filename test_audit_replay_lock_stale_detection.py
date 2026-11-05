
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard
from audit_replay_lock_inspector import ReplayLockInspector


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "guard.db"
        guard = ReplayProcessGuard(db_path)

        tokens = {
            event_id: guard.try_acquire(event_id)
            for event_id in [
                "EVT-ACTIVE",
                "EVT-STALE",
                "EVT-UNKNOWN",
                "EVT-INVALID",
                "EVT-FUTURE",
            ]
        }

        now = datetime.now(timezone.utc)

        with sqlite3.connect(db_path) as conn:
            updates = {
                "EVT-STALE": (
                    now - timedelta(hours=2)
                ).isoformat(),
                "EVT-UNKNOWN": None,
                "EVT-INVALID": "invalid-timestamp",
                "EVT-FUTURE": (
                    now + timedelta(hours=1)
                ).isoformat(),
            }

            for event_id, acquired_at in updates.items():
                conn.execute(
                    """
                    UPDATE REPLAY_ACTIVE_LOCK
                    SET ACQUIRED_AT = ?
                    WHERE EVENT_ID = ?
                    """,
                    (acquired_at, event_id),
                )

        inspector = ReplayLockInspector(
            db_path,
            stale_after_seconds=1800,
        )

        locks = {
            item["event_id"]: item
            for item in inspector.list_active_locks()
        }

        check("FIVE_LOCKS_FOUND", len(locks) == 5)
        check("RECENT_LOCK_ACTIVE", locks["EVT-ACTIVE"]["status"] == "ACTIVE")
        check("OLD_LOCK_SUSPECTED", locks["EVT-STALE"]["status"] == "STALE_SUSPECTED")
        check("NULL_TIME_UNKNOWN", locks["EVT-UNKNOWN"]["status"] == "AGE_UNKNOWN")
        check("INVALID_TIME_UNKNOWN", locks["EVT-INVALID"]["status"] == "AGE_UNKNOWN")
        check("FUTURE_TIME_UNKNOWN", locks["EVT-FUTURE"]["status"] == "AGE_UNKNOWN")
        check(
            "STALE_AGE_RECORDED",
            locks["EVT-STALE"]["age_seconds"] >= 7200,
        )

        # Inspector must never release locks.
        check(
            "INSPECTION_READ_ONLY",
            guard.try_acquire("EVT-STALE") is None,
        )

        for event_id, token in tokens.items():
            guard.release(event_id, token)

        check(
            "ALL_LOCKS_RELEASED",
            inspector.list_active_locks() == [],
        )

    print("[TEST] ALL PASS: Replay Lock Stale Detection")


if __name__ == "__main__":
    main()
