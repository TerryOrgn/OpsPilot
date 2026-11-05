
import os

# 必须在导入业务模块前设置测试库
os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection
from monitor_lock import LOCK_NAME, run_with_monitor_lock


def main():
    # 连接 A：模拟另一个监控实例
    conn_a = get_connection()
    lock_acquired = False

    try:
        with conn_a.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            assert cursor.fetchone()["db"] == "opspilot_test"

            # 连接 A 获取锁
            cursor.execute(
                "SELECT GET_LOCK(%s, 0) AS acquired",
                (LOCK_NAME,)
            )
            acquired = cursor.fetchone()["acquired"]

            assert acquired == 1, (
                f"连接 A 获取锁失败: {acquired}"
            )

            lock_acquired = True

        print("[TEST] CONNECTION_A_LOCK_ACQUIRED=PASS")

        # 连接 B：调用实际封装函数
        monitor_calls = []

        result = run_with_monitor_lock(
            lambda: monitor_calls.append("executed")
        )

        assert result is False, (
            "锁被占用时应返回 False"
        )
        assert monitor_calls == [], (
            "锁被占用时不允许执行监控函数"
        )

        print("[TEST] LOCK_CONTENTION_SKIP=PASS")
        print("[TEST] MONITOR_NOT_EXECUTED=PASS")

        # 验证连接 A 仍然持有锁
        with conn_a.cursor() as cursor:
            cursor.execute(
                "SELECT IS_USED_LOCK(%s) AS owner",
                (LOCK_NAME,)
            )
            owner = cursor.fetchone()["owner"]

            assert owner == conn_a.thread_id(), (
                "连接 A 的锁被其他连接释放"
            )

        print("[TEST] ORIGINAL_LOCK_PRESERVED=PASS")

    finally:
        if lock_acquired:
            try:
                with conn_a.cursor() as cursor:
                    cursor.execute(
                        "SELECT RELEASE_LOCK(%s) AS released",
                        (LOCK_NAME,)
                    )
                    assert cursor.fetchone()["released"] == 1
            finally:
                conn_a.close()
        else:
            conn_a.close()

    # 连接 A 释放后，正常监控应可执行
    calls_after_release = []

    result = run_with_monitor_lock(
        lambda: calls_after_release.append("executed")
    )

    assert result is True
    assert calls_after_release == ["executed"]

    print("[TEST] LOCK_REACQUIRED_AFTER_RELEASE=PASS")
    print("[TEST] ALL PASS: JOB-E2E-8C")


if __name__ == "__main__":
    main()
