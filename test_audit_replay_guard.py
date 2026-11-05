
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from audit_replay_guard import ReplayConcurrencyGuard


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    guard = ReplayConcurrencyGuard()

    check("FIRST_ACQUIRE", guard.try_acquire("EVT-001"))
    check("DUPLICATE_REJECTED", not guard.try_acquire("EVT-001"))
    check("DIFFERENT_EVENT_ALLOWED", guard.try_acquire("EVT-002"))

    guard.release("EVT-001")
    check("REACQUIRE_AFTER_RELEASE", guard.try_acquire("EVT-001"))

    guard.release("EVT-001")
    guard.release("EVT-002")
    guard.release("EVT-UNKNOWN")
    check("RELEASE_IS_IDEMPOTENT", guard.try_acquire("EVT-001"))

    guard.release("EVT-001")

    barrier = Barrier(8)

    def compete():
        barrier.wait()
        return guard.try_acquire("EVT-RACE")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: compete(), range(8)))

    check("ONLY_ONE_WINNER", results.count(True) == 1)
    check("SEVEN_REJECTED", results.count(False) == 7)

    guard.release("EVT-RACE")
    check("AVAILABLE_AFTER_RACE", guard.try_acquire("EVT-RACE"))

    print("[TEST] ALL PASS: Replay Concurrency Guard")


if __name__ == "__main__":
    main()
