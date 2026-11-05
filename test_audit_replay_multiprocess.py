
import multiprocessing as mp
import tempfile
from pathlib import Path

from audit_replay_process_guard import ReplayProcessGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def worker(db_path, event_id, start, results, release):
    guard = ReplayProcessGuard(db_path)

    if not start.wait(timeout=5):
        results.put(("ERROR", "START_TIMEOUT"))
        return

    try:
        token = guard.try_acquire(event_id)

        if token is None:
            results.put(("REJECTED", None))
            return

        results.put(("ACQUIRED", token))

        if not release.wait(timeout=5):
            results.put(("ERROR", "RELEASE_TIMEOUT"))
            return

        guard.release(event_id, token)

    except Exception as exc:
        results.put(("ERROR", type(exc).__name__))


def main():
    ctx = mp.get_context("spawn")

    with tempfile.TemporaryDirectory() as directory:
        db_path = str(Path(directory) / "replay_guard.db")

        # Initialize the shared SQLite database.
        ReplayProcessGuard(db_path)

        start = ctx.Event()
        release = ctx.Event()
        results = ctx.Queue()

        processes = [
            ctx.Process(
                target=worker,
                args=(db_path, "EVT-001", start, results, release),
            )
            for _ in range(2)
        ]

        for process in processes:
            process.start()

        try:
            start.set()

            outcomes = [
                results.get(timeout=8)
                for _ in range(2)
            ]

            statuses = [status for status, _ in outcomes]

            check("TWO_PROCESSES_REPORTED", len(outcomes) == 2)
            check("ONE_PROCESS_ACQUIRED", statuses.count("ACQUIRED") == 1)
            check("ONE_PROCESS_REJECTED", statuses.count("REJECTED") == 1)
            check("NO_PROCESS_ERRORS", "ERROR" not in statuses)

        finally:
            release.set()

            for process in processes:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join()

        check(
            "BOTH_PROCESSES_EXITED",
            all(process.exitcode == 0 for process in processes),
        )

        guard = ReplayProcessGuard(db_path)
        token = guard.try_acquire("EVT-001")

        check("LOCK_RELEASED_AFTER_EXIT", bool(token))

        if token:
            guard.release("EVT-001", token)

    print("[TEST] ALL PASS: Multiprocess Replay Guard")


if __name__ == "__main__":
    main()
