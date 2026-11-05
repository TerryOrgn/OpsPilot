
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "guard.db"

        # Simulate the old BO-8K schema.
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE REPLAY_ACTIVE_LOCK (
                    EVENT_ID TEXT PRIMARY KEY,
                    OWNER_TOKEN TEXT NOT NULL
                )
            """)
            conn.execute(
                """
                INSERT INTO REPLAY_ACTIVE_LOCK
                    (EVENT_ID, OWNER_TOKEN)
                VALUES (?, ?)
                """,
                ("EVT-OLD", "old-owner-token"),
            )

        guard = ReplayProcessGuard(db_path)

        with sqlite3.connect(db_path) as conn:
            columns = [
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(REPLAY_ACTIVE_LOCK)"
                )
            ]

            old_record = conn.execute(
                """
                SELECT OWNER_TOKEN, ACQUIRED_AT
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-OLD",),
            ).fetchone()

        check("COLUMN_ADDED", "ACQUIRED_AT" in columns)
        check("OLD_OWNER_PRESERVED", old_record[0] == "old-owner-token")
        check("OLD_TIMESTAMP_UNKNOWN", old_record[1] is None)

        token = guard.try_acquire("EVT-NEW")
        check("NEW_LOCK_ACQUIRED", bool(token))

        with sqlite3.connect(db_path) as conn:
            acquired_at = conn.execute(
                """
                SELECT ACQUIRED_AT
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-NEW",),
            ).fetchone()[0]

        check("NEW_TIMESTAMP_PRESENT", bool(acquired_at))

        parsed = datetime.fromisoformat(acquired_at)
        check("TIMESTAMP_HAS_TIMEZONE", parsed.tzinfo is not None)
        check(
            "TIMESTAMP_IS_UTC",
            parsed.utcoffset().total_seconds() == 0,
        )

        check(
            "DUPLICATE_STILL_REJECTED",
            guard.try_acquire("EVT-NEW") is None,
        )

        check(
            "WRONG_OWNER_STILL_REJECTED",
            guard.release("EVT-NEW", "wrong-token") is False,
        )

        check("CORRECT_OWNER_RELEASES", guard.release("EVT-NEW", token))
        check(
            "OLD_LOCK_STILL_PRESENT",
            guard.try_acquire("EVT-OLD") is None,
        )

        # Initialization must be safe to repeat.
        ReplayProcessGuard(db_path)
        check("MIGRATION_IDEMPOTENT", True)

        check(
            "OLD_OWNER_CAN_RELEASE",
            guard.release("EVT-OLD", "old-owner-token"),
        )

    print("[TEST] ALL PASS: Replay Lock Timestamp Migration")


if __name__ == "__main__":
    main()
