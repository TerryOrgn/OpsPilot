
import sqlite3
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "guard.db"

        # Simulate the BO-8L database before this migration.
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE REPLAY_ACTIVE_LOCK (
                    EVENT_ID TEXT PRIMARY KEY,
                    OWNER_TOKEN TEXT NOT NULL,
                    ACQUIRED_AT TEXT
                )
            """)
            conn.execute("""
                INSERT INTO REPLAY_ACTIVE_LOCK
                    (EVENT_ID, OWNER_TOKEN, ACQUIRED_AT)
                VALUES (?, ?, ?)
            """, (
                "EVT-OLD",
                "original-owner",
                "2026-10-28T05:00:00+00:00",
            ))

        guard = ReplayProcessGuard(db_path)

        with sqlite3.connect(db_path) as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(REPLAY_ACTIVE_LOCK)"
                )
            }
            old_row = conn.execute("""
                SELECT OWNER_TOKEN, ACQUIRED_AT, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
            """, ("EVT-OLD",)).fetchone()

        check(
            "ATTEMPT_COLUMN_ADDED",
            "REPLAY_ATTEMPT_ID" in columns,
        )
        check(
            "OLD_OWNER_PRESERVED",
            old_row[0] == "original-owner",
        )
        check(
            "OLD_TIMESTAMP_PRESERVED",
            old_row[1] == "2026-10-28T05:00:00+00:00",
        )
        check(
            "OLD_ATTEMPT_UNKNOWN",
            old_row[2] is None,
        )

        token = guard.try_acquire("EVT-NEW")

        check("NEW_LOCK_ACQUIRED", bool(token))

        with sqlite3.connect(db_path) as conn:
            new_row = conn.execute("""
                SELECT ACQUIRED_AT, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
            """, ("EVT-NEW",)).fetchone()

        check("NEW_TIMESTAMP_PRESENT", bool(new_row[0]))
        check("NEW_ATTEMPT_NOT_YET_BOUND", new_row[1] is None)

        check(
            "DUPLICATE_LOCK_REJECTED",
            guard.try_acquire("EVT-NEW") is None,
        )
        check(
            "WRONG_OWNER_REJECTED",
            guard.release("EVT-NEW", "wrong-owner") is False,
        )
        check(
            "CORRECT_OWNER_RELEASED",
            guard.release("EVT-NEW", token) is True,
        )

        # Reinitialization must not repeat the migration.
        ReplayProcessGuard(db_path)

        with sqlite3.connect(db_path) as conn:
            count = sum(
                row[1] == "REPLAY_ATTEMPT_ID"
                for row in conn.execute(
                    "PRAGMA table_info(REPLAY_ACTIVE_LOCK)"
                )
            )

        check("MIGRATION_IDEMPOTENT", count == 1)

        check(
            "OLD_LOCK_STILL_PROTECTED",
            guard.try_acquire("EVT-OLD") is None,
        )
        check(
            "OLD_OWNER_CAN_RELEASE",
            guard.release("EVT-OLD", "original-owner"),
        )

    print("[TEST] ALL PASS: Replay Lock Attempt Schema")


if __name__ == "__main__":
    main()
