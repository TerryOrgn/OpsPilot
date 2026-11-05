
import tempfile
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
        inspector = ReplayLockInspector(db_path)

        check(
            "INITIALLY_EMPTY",
            inspector.list_active_locks() == [],
        )

        token_a = guard.try_acquire("EVT-001")
        token_b = guard.try_acquire("EVT-002")

        locks = inspector.list_active_locks()

        check("TWO_ACTIVE_LOCKS", len(locks) == 2)

        check(
            "EVENT_IDS_PRESERVED",
            [item["event_id"] for item in locks]
            == ["EVT-001", "EVT-002"],
        )

        check(
            "OWNER_TOKENS_PRESERVED",
            [item["owner_token"] for item in locks]
            == [token_a, token_b],
        )

        check(
            "RECENT_LOCKS_ACTIVE",
            all(
                item["status"] == "ACTIVE"
                for item in locks
            ),
        )

        # Inspection must not release active locks.
        check(
            "INSPECTION_IS_READ_ONLY",
            guard.try_acquire("EVT-001") is None,
        )

        guard.release("EVT-001", token_a)

        check(
            "RELEASED_LOCK_DISAPPEARS",
            len(inspector.list_active_locks()) == 1,
        )

        guard.release("EVT-002", token_b)

        check(
            "ALL_LOCKS_RELEASED",
            inspector.list_active_locks() == [],
        )

    print("[TEST] ALL PASS: Replay Lock Inspector")


if __name__ == "__main__":
    main()
