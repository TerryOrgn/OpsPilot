import os
import pymysql

from dotenv import load_dotenv
from datetime import timedelta


load_dotenv()


def get_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.getenv("MYSQL_DATABASE", "opspilot"),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor
    )


def get_job_executions():
    sql = """
        SELECT
            EXECUTION_ID,
            SYSTEM_ID,
            JOB_NAME,
            BUSINESS_DATE,
            START_TIME,
            END_TIME,
            STATUS,
            ERROR_MESSAGE
        FROM JOB_EXECUTION_LOG
        ORDER BY START_TIME DESC
        LIMIT 100
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def get_checkpoint(monitor_name="JOB_MONITOR"):

    sql = """
        SELECT
            MONITOR_NAME,
            LAST_SCAN_TIME,
            LAST_SUCCESS_TIME,
            SCAN_STATUS
        FROM JOB_MONITOR_CHECKPOINT
        WHERE MONITOR_NAME = %s
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, (monitor_name,))
            result = cursor.fetchone()

            if result is None:
                raise ValueError(
                    f"监控水位不存在: {monitor_name}"
                )

            return result

    finally:
        connection.close()


def get_incremental_jobs(
    last_scan_time,
    overlap_minutes=5
):
    """
    查询上次水位之后新增或更新的JOB。

    返回：
        jobs: JOB记录列表
        scan_upper_bound: 本次扫描上界
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:

            # 使用MySQL时间作为扫描上界
            cursor.execute(
                "SELECT NOW(3) AS scan_time"
            )

            scan_upper_bound = cursor.fetchone()["scan_time"]

            # 向前回溯5分钟
            scan_start = last_scan_time - timedelta(
                minutes=overlap_minutes
            )

            sql = """
                SELECT
                    ID,
                    EXECUTION_ID,
                    SYSTEM_ID,
                    JOB_NAME,
                    BUSINESS_DATE,
                    START_TIME,
                    END_TIME,
                    STATUS,
                    ERROR_MESSAGE,
                    UPDATED_AT
                FROM JOB_EXECUTION_LOG
                WHERE UPDATED_AT >= %s
                  AND UPDATED_AT <= %s
                ORDER BY UPDATED_AT, ID
            """

            cursor.execute(
                sql,
                (scan_start, scan_upper_bound)
            )

            jobs = cursor.fetchall()

            return jobs, scan_upper_bound

    finally:
        connection.close()


def update_checkpoint(
    scan_upper_bound,
    monitor_name="JOB_MONITOR"
):
    """
    本轮JOB处理全部成功后，更新扫描水位。
    """

    sql = """
        UPDATE JOB_MONITOR_CHECKPOINT
        SET
            LAST_SCAN_TIME = %s,
            LAST_SUCCESS_TIME = NOW(3),
            SCAN_STATUS = 'SUCCESS',
            LAST_ERROR_MESSAGE = NULL
        WHERE MONITOR_NAME = %s
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                (scan_upper_bound, monitor_name)
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "更新监控水位失败"
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def get_running_jobs():

    sql = """
        SELECT
            ID,
            EXECUTION_ID,
            SYSTEM_ID,
            JOB_NAME,
            BUSINESS_DATE,
            START_TIME,
            END_TIME,
            STATUS,
            ERROR_MESSAGE,
            UPDATED_AT
        FROM JOB_EXECUTION_LOG
        WHERE STATUS = 'RUNNING'
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()


def get_job_by_execution_id(execution_id):

    sql = """
        SELECT
            ID,
            EXECUTION_ID,
            SYSTEM_ID,
            JOB_NAME,
            BUSINESS_DATE,
            START_TIME,
            END_TIME,
            STATUS,
            ERROR_MESSAGE,
            UPDATED_AT
        FROM JOB_EXECUTION_LOG
        WHERE EXECUTION_ID = %s
    """

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, (execution_id,))
            return cursor.fetchone()

    finally:
        connection.close()