
import os
import uuid
from datetime import datetime

os.environ["MYSQL_DATABASE"] = "opspilot_test"

from db import get_connection, get_incremental_jobs


def main():
    execution_id = "E2E6F_" + uuid.uuid4().hex[:16]

    # 模拟上一轮扫描水位
    checkpoint = datetime(2026, 10, 30, 10, 0, 0, 800000)

    # 秒级 UPDATED_AT 比水位早 800ms
    updated_at = datetime(2026, 10, 30, 10, 0, 0)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            database = cursor.fetchone()["db"]
            assert database == "opspilot_test"

            cursor.execute(
                """
                INSERT INTO JOB_EXECUTION_LOG
                    (EXECUTION_ID, SYSTEM_ID, JOB_NAME,
                     BUSINESS_DATE, START_TIME, END_TIME,
                     STATUS, UPDATED_AT)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    "E2E_TEST",
                    "PrecisionBoundaryJob",
                    "2026-10-30",
                    "2026-10-30 09:59:00",
                    "2026-10-30 10:00:00",
                    "SUCCESS",
                    updated_at,
                ),
            )

        connection.commit()

        # 无重叠扫描
        jobs_no_overlap, _ = get_incremental_jobs(
            checkpoint,
            overlap_minutes=0
        )

        # 当前生产策略：5分钟重叠
        jobs_with_overlap, _ = get_incremental_jobs(
            checkpoint,
            overlap_minutes=5
        )

        found_no_overlap = any(
            job["EXECUTION_ID"] == execution_id
            for job in jobs_no_overlap
        )

        found_with_overlap = any(
            job["EXECUTION_ID"] == execution_id
            for job in jobs_with_overlap
        )

        print("DATABASE:", database)
        print("EXECUTION_ID:", execution_id)
        print("CHECKPOINT:", checkpoint)
        print("UPDATED_AT:", updated_at)
        print("NO_OVERLAP_FOUND:", found_no_overlap)
        print("FIVE_MIN_OVERLAP_FOUND:", found_with_overlap)

        assert not found_no_overlap, (
            "无重叠场景未出现预期的边界遗漏"
        )
        assert found_with_overlap, (
            "5分钟重叠窗口未能覆盖边界JOB"
        )

        print("[TEST] JOB-E2E-6F: PASS")

    finally:
        # 清理本次创建的测试 JOB
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM JOB_EXECUTION_LOG
                    WHERE EXECUTION_ID = %s
                    """,
                    (execution_id,)
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


if __name__ == "__main__":
    main()
