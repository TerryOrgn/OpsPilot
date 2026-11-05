
import os
import threading
from concurrent.futures import ThreadPoolExecutor

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection

LOCK_NAME = "opspilot:e2e8a:monitor"


def worker(name, barrier, release_event):
    conn = get_connection()
    acquired = False

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            assert cursor.fetchone()["db"] == "opspilot_test"

        # 两个线程同时开始竞争
        barrier.wait(timeout=10)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT GET_LOCK(%s, 0) AS acquired",
                (LOCK_NAME,)
            )
            result = cursor.fetchone()["acquired"]

        if result is None:
            raise RuntimeError("GET_LOCK returned NULL")

        acquired = result == 1

        if acquired:
            # 持锁直到主线程允许释放
            if not release_event.wait(timeout=10):
                raise TimeoutError("等待释放锁超时")

        return name, acquired

    finally:
        if acquired:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT RELEASE_LOCK(%s) AS released",
                        (LOCK_NAME,)
                    )
                    released = cursor.fetchone()["released"]
                    if released != 1:
                        raise RuntimeError(
                            f"释放命名锁失败: {released}"
                        )
            finally:
                conn.close()
        else:
            conn.close()


def main():
    barrier = threading.Barrier(2)
    release_event = threading.Event()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                worker, "WORKER_A", barrier, release_event
            ),
            executor.submit(
                worker, "WORKER_B", barrier, release_event
            ),
        ]

        # 让两个线程完成锁竞争
        # 通过短暂等待确保竞争结果可观察
        import time
        time.sleep(1)
        release_event.set()

        results = [future.result() for future in futures]

    print("RESULTS:", results)

    acquired_count = sum(
        1 for _, acquired in results if acquired
    )

    assert acquired_count == 1, (
        f"预期只有一个持锁者，实际 {acquired_count}"
    )

    print("[TEST] ONLY_ONE_LOCK_OWNER=PASS")
    print("[TEST] ALL PASS: JOB-E2E-8A")


if __name__ == "__main__":
    main()
