
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

# 必须在导入业务模块前设置
os.environ["MYSQL_DATABASE"] = "opspilot_test"

import alert_manager
from db import get_connection


def test_concurrent_alert_creation():
    # 1. 强制验证测试库
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            database = cursor.fetchone()["db"]

    assert database == "opspilot_test", (
        f"禁止在非测试库执行: {database}"
    )

    # 2. 每次生成独立的测试执行 ID
    execution_id = "E2E6D_" + uuid.uuid4().hex[:16]

    job = {
        "EXECUTION_ID": execution_id,
        "SYSTEM_ID": "E2E_TEST",
        "JOB_NAME": "ConcurrentTestJob",
    }


    # JOB-E2E-6D: 创建合法的测试 JOB，满足外键约束
    # 仅操作 opspilot_test，不修改 Checkpoint
    from datetime import datetime, timedelta

    now = datetime.now()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE() AS db"
            )
            assert cursor.fetchone()["db"] == "opspilot_test"

            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG (
                    EXECUTION_ID,
                    SYSTEM_ID,
                    JOB_NAME,
                    BUSINESS_DATE,
                    START_TIME,
                    END_TIME,
                    STATUS,
                    ERROR_MESSAGE
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, 'FAILED', %s
                )
                """,
                (
                    execution_id,
                    job["SYSTEM_ID"],
                    job["JOB_NAME"],
                    now.date(),
                    now - timedelta(minutes=5),
                    now,
                    "E2E-6D simulated job failure"
                )
            )

        # 先提交，确保两个并发连接都能读取该 JOB
        conn.commit()

    print("[SETUP] 测试 JOB 创建成功:", execution_id)


    barrier = threading.Barrier(2, timeout=10)

    def worker(worker_id):
        try:
            # 两个线程尽量同时调用
            barrier.wait()

            result = alert_manager.save_alert(
                job,
                "JOB_FAILED",
                "CRITICAL",
                "E2E-6D concurrent failure"
            )

            return {
                "worker": worker_id,
                "result": result,
                "error": None,
            }

        except Exception as exc:
            return {
                "worker": worker_id,
                "result": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

    # 3. 两个并发线程
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, i)
            for i in (1, 2)
        ]
        results = [f.result() for f in futures]

    # 4. 检查数据库最终状态
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ID, ALERT_STATUS, DETECT_COUNT
                FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                  AND ALERT_TYPE = 'JOB_FAILED'
                """,
                (execution_id,)
            )
            alerts = cursor.fetchall()

            audit_count = 0
            notification_count = 0

            if len(alerts) == 1:
                alert_id = alerts[0]["ID"]

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM JOB_ALERT_STATUS_HISTORY
                    WHERE ALERT_ID = %s
                    """,
                    (alert_id,)
                )
                audit_count = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM JOB_NOTIFICATION_HISTORY
                    WHERE ALERT_ID = %s
                    """,
                    (alert_id,)
                )
                notification_count = cursor.fetchone()["cnt"]

    # 5. 输出诊断
    print("\n========== JOB-E2E-6D ==========")
    print("DATABASE:", database)
    print("EXECUTION_ID:", execution_id)

    for item in results:
        print("WORKER:", item)

    print("ALERT_COUNT:", len(alerts))
    print("ALERTS:", alerts)
    print("AUDIT_COUNT:", audit_count)
    print("NOTIFICATION_COUNT:", notification_count)

    event_types = Counter(
        r["result"]["event_type"]
        for r in results
        if r["result"] is not None
    )

    no_errors = all(r["error"] is None for r in results)

    passed = (
        no_errors
        and len(alerts) == 1
        and alerts[0]["ALERT_STATUS"] == "OPEN"
        and alerts[0]["DETECT_COUNT"] == 2
        and event_types == Counter({
            "CREATED": 1,
            "DUPLICATE": 1,
        })
        and audit_count == 1
        and notification_count == 1
    )

    print(
        "JOB-E2E-6D:",
        "PASS" if passed else "FAIL"
    )

    assert passed, "并发告警创建验收失败"


if __name__ == "__main__":
    test_concurrent_alert_creation()
