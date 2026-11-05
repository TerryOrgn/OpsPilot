
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

# 必须在导入业务模块前指定测试库
os.environ["MYSQL_DATABASE"] = "opspilot_test"

import job_monitor
from db import get_connection, get_checkpoint, update_checkpoint


def main():
    execution_id = "E2E7A_" + uuid.uuid4().hex[:16]
    monitor_name = "E2E7A_" + uuid.uuid4().hex[:12]

    # 使用数据库时间，避免本机与 MySQL 时钟不一致
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db, NOW(3) AS now_time")
            row = cursor.fetchone()

            assert row["db"] == "opspilot_test"
            db_now = row["now_time"]

            start_time = db_now - timedelta(minutes=10)
            end_time = db_now - timedelta(minutes=9)
            initial_checkpoint = db_now - timedelta(minutes=15)

            cursor.execute(
                """
                INSERT INTO JOB_MONITOR_CHECKPOINT
                    (MONITOR_NAME, LAST_SCAN_TIME, SCAN_STATUS)
                VALUES (%s, %s, 'IDLE')
                """,
                (monitor_name, initial_checkpoint)
            )

            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG
                    (EXECUTION_ID, SYSTEM_ID, JOB_NAME,
                     BUSINESS_DATE, START_TIME, END_TIME,
                     STATUS, ERROR_MESSAGE)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    "E2E_TEST",
                    "E2E7A_FailedJob",
                    db_now.date(),
                    start_time,
                    end_time,
                    "FAILED",
                    "E2E7A simulated database timeout"
                )
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[TEST] DATABASE_ISOLATION=PASS")
    print("[SETUP] EXECUTION_ID:", execution_id)
    print("[SETUP] MONITOR_NAME:", monitor_name)

    # 只替换 Checkpoint 访问，不替换扫描、告警、恢复逻辑
    with (
        patch.object(
            job_monitor,
            "get_checkpoint",
            side_effect=lambda: get_checkpoint(monitor_name)
        ),
        patch.object(
            job_monitor,
            "update_checkpoint",
            side_effect=lambda upper_bound: update_checkpoint(
                upper_bound,
                monitor_name=monitor_name
            )
        ),
    ):
        # 第一次：创建告警
        job_monitor.monitor_jobs()

        first_checkpoint = get_checkpoint(monitor_name)

        conn = get_connection()
        try:
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
                first_alert = cursor.fetchone()
        finally:
            conn.close()

        assert first_alert is not None, "未创建 JOB_FAILED 告警"
        assert first_alert["ALERT_STATUS"] == "OPEN"
        assert first_alert["DETECT_COUNT"] == 1
        assert (
            first_checkpoint["LAST_SCAN_TIME"] > initial_checkpoint
        ), "Checkpoint 未推进"

        print("[TEST] FIRST_ALERT_CREATED=PASS")
        print("[TEST] FIRST_CHECKPOINT_ADVANCED=PASS")

        # 第二次：应当复用同一条告警
        job_monitor.monitor_jobs()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt,
                       MAX(DETECT_COUNT) AS detect_count
                FROM JOB_ALERT_HISTORY
                WHERE EXECUTION_ID = %s
                  AND ALERT_TYPE = 'JOB_FAILED'
                """,
                (execution_id,)
            )
            result = cursor.fetchone()

        assert result["cnt"] == 1, "重复生成了告警记录"
        assert result["detect_count"] == 2, (
            "第二次扫描未触发 DUPLICATE"
        )

        print("[TEST] ALERT_DEDUPLICATION=PASS")
        print("[TEST] DETECT_COUNT_TWO=PASS")
        print("[TEST] ALL PASS: JOB-E2E-7A")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
