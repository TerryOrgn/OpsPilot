
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
        guard = ReplayProcessGuard(db_path)

        token = guard.try_acquire(
            "EVT-001",
            replay_attempt_id="ATTEMPT-A",
        )

        check("LOCK_ACQUIRED", bool(token))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT OWNER_TOKEN, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-001",),
            ).fetchone()

        check("OWNER_PRESERVED", row[0] == token)
        check("ATTEMPT_BOUND", row[1] == "ATTEMPT-A")

        check(
            "DUPLICATE_REJECTED",
            guard.try_acquire(
                "EVT-001",
                replay_attempt_id="ATTEMPT-B",
            ) is None,
        )

        with sqlite3.connect(db_path) as conn:
            stored_attempt = conn.execute(
                """
                SELECT REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-001",),
            ).fetchone()[0]

        check(
            "FAILED_ACQUIRE_CANNOT_OVERWRITE",
            stored_attempt == "ATTEMPT-A",
        )

        check(
            "INVALID_ATTEMPT_REJECTED",
            _invalid_attempt_rejected(guard),
        )

        check(
            "WRONG_OWNER_CANNOT_RELEASE",
            guard.release("EVT-001", "wrong-owner") is False,
        )

        check(
            "CORRECT_OWNER_RELEASES",
            guard.release("EVT-001", token) is True,
        )

        new_token = guard.try_acquire(
            "EVT-001",
            replay_attempt_id="ATTEMPT-C",
        )

        check("REACQUIRE_ALLOWED", bool(new_token))

        with sqlite3.connect(db_path) as conn:
            new_attempt = conn.execute(
                """
                SELECT REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-001",),
            ).fetchone()[0]

        check("NEW_ATTEMPT_BOUND", new_attempt == "ATTEMPT-C")

        check(
            "OLD_OWNER_CANNOT_RELEASE",
            guard.release("EVT-001", token) is False,
        )

        check(
            "NEW_OWNER_RELEASES",
            guard.release("EVT-001", new_token) is True,
        )

    print("[TEST] ALL PASS: Replay Process Attempt Binding")


def _invalid_attempt_rejected(guard):
    try:
        guard.try_acquire("EVT-INVALID", replay_attempt_id="")
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    main()
