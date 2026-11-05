
import os
import uuid
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# 必须在导入 db 之前设置测试库
os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection, get_checkpoint, update_checkpoint


INITIAL = datetime(2026, 10, 30, 10, 0, 0)
NEWER = datetime(2026, 10, 30, 10, 5, 0)
OLDER = datetime(2026, 10, 30, 10, 2, 0)


def main():
    monitor_name = "E2E6E_" + uuid.uuid4().hex[:12]

    # 1. 检查真实数据库连接
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            db_name = cursor.fetchone()["db"]
            assert db_name == "opspilot_test", db_name
    finally:
        conn.close()

    print("[TEST] DATABASE_ISOLATION=PASS")

    # 2. 初始化独立测试 Checkpoint
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_CHECKPOINT
                    (MONITOR_NAME, LAST_SCAN_TIME,
                     LAST_SUCCESS_TIME, SCAN_STATUS)
                VALUES (%s, %s, %s, 'SUCCESS')
                """,
                (monitor_name, INITIAL, INITIAL)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[SETUP] MONITOR_NAME:", monitor_name)

    # 3. 并发更新
    barrier = threading.Barrier(2, timeout=10)

    def worker(name, target):
        try:
            barrier.wait()
            update_checkpoint(
                target,
                monitor_name=monitor_name
            )
            return (name, "SUCCESS", None)
        except Exception as exc:
            return (name, "ERROR", repr(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, "A_NEWER", NEWER),
            pool.submit(worker, "B_OLDER", OLDER),
        ]
        results = [f.result() for f in futures]

    # 4. 查询最终 Checkpoint
    checkpoint = get_checkpoint(monitor_name)
    final_time = checkpoint["LAST_SCAN_TIME"]

    print("\n========== JOB-E2E-6E ==========")
    print("DATABASE:", db_name)
    print("MONITOR_NAME:", monitor_name)
    print("INITIAL:", INITIAL)
    print("A_NEWER:", NEWER)
    print("B_OLDER:", OLDER)

    for result in results:
        print("WORKER:", result)

    print("FINAL_CHECKPOINT:", final_time)

    # 5. 验收
    no_errors = all(r[1] == "SUCCESS" for r in results)
    correct_watermark = final_time == NEWER

    print(
        "[TEST] BOTH_WORKERS_SUCCESS=",
        "PASS" if no_errors else "FAIL"
    )
    print(
        "[TEST] CHECKPOINT_NO_ROLLBACK=",
        "PASS" if correct_watermark else "FAIL"
    )

    assert no_errors, "并发更新出现异常"
    assert correct_watermark, "Checkpoint 发生水位回退"

    print("[TEST] ALL PASS: JOB-E2E-6E")


if __name__ == "__main__":
    main()
