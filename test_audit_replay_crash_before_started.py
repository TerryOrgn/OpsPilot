
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


CHILD_CODE = """
import os
import sys

from audit_replay_process_guard import ReplayProcessGuard

db_path = sys.argv[1]
guard = ReplayProcessGuard(db_path)

token = guard.try_acquire(
    "EVT-CRASH",
    replay_attempt_id="ATTEMPT-CRASH-001",
)

if not token:
    sys.exit(2)

# Simulate an abrupt process termination before STARTED audit.
os._exit(37)
"""


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        db_path = directory / "guard.db"
        operation_path = directory / "operations.jsonl"

        child = subprocess.run(
            [sys.executable, "-c", CHILD_CODE, str(db_path)],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
        )

        check("CHILD_CRASHED", child.returncode == 37)

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT OWNER_TOKEN, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-CRASH",),
            ).fetchone()

        check("LOCK_SURVIVED_CRASH", row is not None)
        check(
            "ATTEMPT_SURVIVED_CRASH",
            row is not None
            and row[1] == "ATTEMPT-CRASH-001",
        )

        guard = ReplayProcessGuard(db_path)

        check(
            "NEW_REPLAY_BLOCKED",
            guard.try_acquire(
                "EVT-CRASH",
                replay_attempt_id="ATTEMPT-NEW",
            ) is None,
        )

        with sqlite3.connect(db_path) as conn:
            stored_attempt = conn.execute(
                """
                SELECT REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-CRASH",),
            ).fetchone()[0]

        check(
            "CRASH_ATTEMPT_NOT_OVERWRITTEN",
            stored_attempt == "ATTEMPT-CRASH-001",
        )

        entries = []
        if operation_path.exists():
            entries = [
                json.loads(line)
                for line in operation_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        check("NO_STARTED_AUDIT", entries == [])

        # Deliberately do not release the orphaned lock.
        check(
            "LOCK_REQUIRES_MANUAL_REVIEW",
            guard.try_acquire("EVT-CRASH") is None,
        )

    print("[TEST] ALL PASS: Crash Before STARTED")


if __name__ == "__main__":
    main()
