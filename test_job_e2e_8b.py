
import os

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection
from monitor_lock import LOCK_NAME, run_with_monitor_lock


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            assert cursor.fetchone()["db"] == "opspilot_test"
    finally:
        conn.close()

    # 1. 正常执行
    called = []

    result = run_with_monitor_lock(
        lambda: called.append("executed")
    )

    assert result is True
    assert called == ["executed"]
    print("[TEST] NORMAL_EXECUTION=PASS")

    # 2. 监控函数异常
    def failing_monitor():
        raise ValueError("Simulated monitor failure")

    try:
        run_with_monitor_lock(failing_monitor)
        raise AssertionError("预期异常没有抛出")
    except ValueError as exc:
        assert str(exc) == "Simulated monitor failure"

    # 3. 验证异常后锁已释放
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT GET_LOCK(%s, 0) AS acquired",
                (LOCK_NAME,)
            )
            acquired = cursor.fetchone()["acquired"]

            assert acquired == 1, "异常后锁未释放"

            cursor.execute(
                "SELECT RELEASE_LOCK(%s) AS released",
                (LOCK_NAME,)
            )
            assert cursor.fetchone()["released"] == 1
    finally:
        conn.close()

    print("[TEST] EXCEPTION_RELEASE=PASS")
    print("[TEST] ALL PASS: JOB-E2E-8B")


if __name__ == "__main__":
    main()
