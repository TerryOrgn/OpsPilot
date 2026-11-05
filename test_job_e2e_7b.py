
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

# 必须在导入业务模块之前指定测试库
os.environ["MYSQL_DATABASE"] = "opspilot_test"

import job_monitor
from db import get_connection, get_checkpoint, update_checkpoint


def read_alert(execution_id):
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
            return cursor.fetchone()
    finally:
        conn.close()


def main():
    execution_id = "E2E7B_" + uuid.uuid4().hex[:16]
    monitor_name = "E2E7B_" + uuid.uuid4().hex[:12]

    # 1. 初始化独立测试数据
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE() AS db, NOW(3) AS now_time"
            )
            row = cursor.fetchone()

            assert row["db"] == "opspilot_test"
            now = row["now_time"]

            initial_checkpoint = now - timedelta(minutes=15)

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
                    "E2E7B_FailedJob",
                    now.date(),
                    now - timedelta(minutes=10),
                    now - timedelta(minutes=9),
                    "FAILED",
                    "E2E7B simulated database timeout"
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

    # 2. 仅替换 Checkpoint 访问函数
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
        # 3. 第一次：模拟告警保存失败
        original_save_alert = job_monitor.save_alert

        def failing_save_alert(job, *args, **kwargs):
            if job["EXECUTION_ID"] == execution_id:
                raise RuntimeError(
                    "E2E7B simulated alert persistence failure"
                )
            return original_save_alert(job, *args, **kwargs)

        failed_as_expected = False

        with patch.object(
            job_monitor,
            "save_alert",
            side_effect=failing_save_alert
        ):
            try:
                job_monitor.monitor_jobs()
            except RuntimeError as exc:
                if "E2E7B simulated" not in str(exc):
                    raise
                failed_as_expected = True

        assert failed_as_expected, (
            "监控没有抛出预期的持久化异常"
        )

        checkpoint_after_failure = get_checkpoint(monitor_name)

        assert (
            checkpoint_after_failure["LAST_SCAN_TIME"]
            == initial_checkpoint
        ), "故障后 Checkpoint 被错误推进"

        assert read_alert(execution_id) is None, (
            "故障注入后不应生成目标告警"
        )

        print("[TEST] FAILURE_PROPAGATED=PASS")
        print("[TEST] CHECKPOINT_UNCHANGED=PASS")
        print("[TEST] NO_ALERT_AFTER_FAILURE=PASS")

        # 4. 第二次：恢复正常监控
        job_monitor.monitor_jobs()

    checkpoint_after_recovery = get_checkpoint(monitor_name)
    alert = read_alert(execution_id)

    assert alert is not None, "恢复后未生成告警"
    assert alert["ALERT_STATUS"] == "OPEN"
    assert alert["DETECT_COUNT"] == 1
    assert (
        checkpoint_after_recovery["LAST_SCAN_TIME"]
        > initial_checkpoint
    ), "恢复后 Checkpoint 未推进"

    print("[TEST] ALERT_CREATED_AFTER_RECOVERY=PASS")
    print("[TEST] CHECKPOINT_ADVANCED_AFTER_RECOVERY=PASS")
    print("[TEST] ALL PASS: JOB-E2E-7B")


if __name__ == "__main__":
    main()
