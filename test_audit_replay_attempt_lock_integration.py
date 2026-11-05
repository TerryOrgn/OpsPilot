
import json
import sqlite3
import tempfile
from pathlib import Path

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class InspectingRetryService:
    def __init__(self, db_path, operation_path):
        self.db_path = db_path
        self.operation_path = operation_path
        self.calls = 0
        self.observed_lock = None
        self.observed_started = None

    def execute(self, audit):
        self.calls += 1
        event_id = audit["event_id"]

        # Read the active lock while replay is executing.
        with sqlite3.connect(self.db_path) as conn:
            self.observed_lock = conn.execute(
                """
                SELECT OWNER_TOKEN, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                (event_id,),
            ).fetchone()

        # Read the STARTED audit before replay completes.
        entries = [
            json.loads(line)
            for line in self.operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        started = [
            entry for entry in entries
            if entry["event_id"] == event_id
            and entry["status"] == "STARTED"
        ]

        self.observed_started = started[-1] if started else None

        return {
            "status": "SUCCESS",
            "event_id": event_id,
            "attempts": 1,
        }


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)

        db_path = directory / "replay_locks.db"
        dead_path = directory / "dead_letters.jsonl"
        operation_path = directory / "operations.jsonl"

        DeadLetterRecorder(dead_path).record(
            {
                "event_id": "EVT-001",
                "event": "JOB_MONITORING_SUMMARY",
            },
            {
                "status": "FAILED",
                "event_id": "EVT-001",
                "last_error_type": "ConnectionError",
            },
        )

        retry = InspectingRetryService(db_path, operation_path)

        service = DeadLetterReplayService(
            dead_path,
            retry,
            operation_recorder=ReplayOperationRecorder(
                operation_path
            ),
            process_guard=ReplayProcessGuard(db_path),
        )

        result = service.replay(
            "EVT-001",
            approved=True,
            actor="operator-A",
        )

        check("REPLAY_SUCCESS", result["status"] == "SUCCESS")
        check("ONE_EXECUTION", retry.calls == 1)

        lock = retry.observed_lock
        started = retry.observed_started

        check("LOCK_VISIBLE_DURING_EXECUTION", lock is not None)
        check("STARTED_VISIBLE_DURING_EXECUTION", started is not None)

        lock_attempt_id = lock[1] if lock else None
        audit_attempt_id = (
            started.get("replay_attempt_id")
            if started else None
        )

        check(
            "LOCK_ATTEMPT_ID_PRESENT",
            bool(lock_attempt_id),
        )
        check(
            "AUDIT_ATTEMPT_ID_PRESENT",
            bool(audit_attempt_id),
        )
        check(
            "LOCK_AND_AUDIT_MATCH",
            bool(lock_attempt_id)
            and lock_attempt_id == audit_attempt_id,
        )

        entries = [
            json.loads(line)
            for line in operation_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        check(
            "AUDIT_ORDER",
            [entry["status"] for entry in entries]
            == ["STARTED", "SUCCESS"],
        )
        check(
            "TERMINAL_ATTEMPT_MATCHES",
            entries[1].get("replay_attempt_id")
            == lock_attempt_id,
        )

        with sqlite3.connect(db_path) as conn:
            remaining = conn.execute(
                """
                SELECT COUNT(*)
                FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                """,
                ("EVT-001",),
            ).fetchone()[0]

        check("LOCK_RELEASED_AFTER_SUCCESS", remaining == 0)

    print("[TEST] ALL PASS: Replay Attempt Lock Integration")


if __name__ == "__main__":
    main()
