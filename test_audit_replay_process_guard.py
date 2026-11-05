
import sqlite3
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "replay_guard.db"

        guard_a = ReplayProcessGuard(db_path)
        guard_b = ReplayProcessGuard(db_path)

        token_a = guard_a.try_acquire("EVT-001")

        check("FIRST_ACQUIRE", bool(token_a))

        check(
            "DUPLICATE_REJECTED",
            guard_b.try_acquire("EVT-001") is None,
        )

        token_b = guard_b.try_acquire("EVT-002")

        check("DIFFERENT_EVENT_ALLOWED", bool(token_b))

        check(
            "WRONG_OWNER_CANNOT_RELEASE",
            guard_b.release("EVT-001", "wrong-token") is False,
        )

        check(
            "STILL_LOCKED_AFTER_WRONG_OWNER",
            guard_b.try_acquire("EVT-001") is None,
        )

        check(
            "OWNER_CAN_RELEASE",
            guard_a.release("EVT-001", token_a),
        )

        token_new = guard_b.try_acquire("EVT-001")

        check("REACQUIRE_AFTER_RELEASE", bool(token_new))

        check(
            "OLD_OWNER_CANNOT_RELEASE_NEW_LOCK",
            guard_a.release("EVT-001", token_a) is False,
        )

        check(
            "NEW_OWNER_CAN_RELEASE",
            guard_b.release("EVT-001", token_new),
        )

        check(
            "OTHER_EVENT_RELEASE",
            guard_b.release("EVT-002", token_b),
        )

        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM REPLAY_ACTIVE_LOCK"
            ).fetchone()[0]

        check("NO_ACTIVE_LOCKS", count == 0)

    print("[TEST] ALL PASS: Replay Process Guard")


if __name__ == "__main__":
    main()
