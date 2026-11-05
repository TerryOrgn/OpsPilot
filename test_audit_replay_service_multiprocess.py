
import multiprocessing as mp
import tempfile
from pathlib import Path
from queue import Empty

from audit_dead_letter_recorder import DeadLetterRecorder
from audit_dead_letter_replay_service import DeadLetterReplayService
from audit_replay_operation_recorder import ReplayOperationRecorder
from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


class BlockingRetryService:
    def __init__(self, started, release):
        self.started = started
        self.release = release

    def execute(self, audit):
        self.started.set()

        if not self.release.wait(timeout=10):
            raise TimeoutError("Replay test timed out")

        return {
            "status": "SUCCESS",
            "event_id": audit["event_id"],
            "attempts": 1,
        }


class ForbiddenRetryService:
    def execute(self, audit):
        raise AssertionError("Second process must not execute")


def first_worker(db_path, dead_path, audit_path, started, release, results):
    try:
        service = DeadLetterReplayService(
            dead_path,
            BlockingRetryService(started, release),
            operation_recorder=ReplayOperationRecorder(audit_path),
            process_guard=ReplayProcessGuard(db_path),
        )

        result = service.replay("EVT-001", approved=True, actor="process-A")
        results.put(result)
    except Exception as exc:
        results.put({
            "status": "ERROR",
            "reason": type(exc).__name__,
        })


def main():
    ctx = mp.get_context("spawn")

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        db_path = directory / "guard.db"
        dead_path = directory / "dead_letters.jsonl"
        audit_path = directory / "operations.jsonl"

        DeadLetterRecorder(dead_path).record(
            {"event_id": "EVT-001", "event": "JOB_MONITORING_SUMMARY"},
            {
                "status": "FAILED",
                "event_id": "EVT-001",
                "last_error_type": "ConnectionError",
            },
        )

        ReplayProcessGuard(db_path)

        started = ctx.Event()
        release = ctx.Event()
        results = ctx.Queue()

        process = ctx.Process(
            target=first_worker,
            args=(
                db_path, dead_path, audit_path,
                started, release, results,
            ),
        )
        process.start()

        try:
            check("FIRST_PROCESS_ENTERED_RETRY", started.wait(timeout=5))

            second_service = DeadLetterReplayService(
                dead_path,
                ForbiddenRetryService(),
                operation_recorder=ReplayOperationRecorder(audit_path),
                process_guard=ReplayProcessGuard(db_path),
            )

            second = second_service.replay(
                "EVT-001",
                approved=True,
                actor="process-B",
            )

            check("SECOND_PROCESS_REJECTED", second["status"] == "REJECTED")
            check(
                "PROCESS_GUARD_REASON",
                second["reason"] == "REPLAY_ALREADY_IN_PROGRESS",
            )

        finally:
            release.set()
            process.join(timeout=5)

            if process.is_alive():
                process.terminate()
                process.join()

        check("FIRST_PROCESS_EXITED", process.exitcode == 0)

        try:
            first = results.get(timeout=2)
        except Empty:
            raise AssertionError("First process did not return a result")

        check("FIRST_REPLAY_SUCCESS", first["status"] == "SUCCESS")

        guard = ReplayProcessGuard(db_path)
        token = guard.try_acquire("EVT-001")

        check("PROCESS_LOCK_RELEASED", bool(token))

        if token:
            guard.release("EVT-001", token)

    print("[TEST] ALL PASS: ReplayService Multiprocess")


if __name__ == "__main__":
    main()
