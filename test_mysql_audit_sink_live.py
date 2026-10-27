
import uuid

from mysql.connector import Error
import os
import mysql.connector


from job_audit_recorder import JobAuditRecorder
from mysql_audit_sink import MySQLAuditSink

from dotenv import load_dotenv

load_dotenv()


def create_connection():
    # TODO:
    # 复制 test_mysql_job_repository_live.py
    # 中已经验证成功的 mysql.connector 连接代码。
    #
    # 必须返回一个新的 MySQL Connection。
    # 不要在这里硬编码数据库密码。
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
    )


def check(name, condition):
    assert condition, name
    print(f"[LIVE] {name}=PASS")


request_id = "REQ-BO2B-" + uuid.uuid4().hex[:16]

audit = {
    "request_id": request_id,
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 15,
    "returned_count": 10,
    "truncated": True,
    "summary_status": "SUCCESS",
}

sink = MySQLAuditSink(
    connection_factory=create_connection
)

recorder = JobAuditRecorder(sink)

connection = None

try:
    # 1. 真实写入
    check(
        "AUDIT_RECORD_SUCCESS",
        recorder.record(audit) is True,
    )

    # 2. 使用独立连接验证提交后的数据
    connection = create_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                REQUEST_ID,
                EVENT,
                TOOL_NAME,
                TOTAL_ABNORMAL_COUNT,
                RETURNED_COUNT,
                TRUNCATED,
                SUMMARY_STATUS,
                CREATED_AT
            FROM AGENT_AUDIT_LOG
            WHERE REQUEST_ID = %s
            """,
            (request_id,),
        )

        rows = cursor.fetchall()

    finally:
        cursor.close()

    check(
        "RECORD_FOUND",
        len(rows) == 1,
    )

    saved = rows[0]

    check(
        "REQUEST_ID_MATCHES",
        saved["REQUEST_ID"] == request_id,
    )

    check(
        "EVENT_MATCHES",
        saved["EVENT"] == audit["event"],
    )

    check(
        "TOOL_NAME_MATCHES",
        saved["TOOL_NAME"] == audit["tool_name"],
    )

    check(
        "COUNTS_MATCH",
        saved["TOTAL_ABNORMAL_COUNT"] == 15
        and saved["RETURNED_COUNT"] == 10,
    )

    check(
        "TRUNCATED_MATCHES",
        saved["TRUNCATED"] == 1,
    )

    check(
        "SUMMARY_STATUS_MATCHES",
        saved["SUMMARY_STATUS"] == "SUCCESS",
    )

    check(
        "CREATED_AT_EXISTS",
        saved["CREATED_AT"] is not None,
    )

    print(f"[LIVE] REQUEST_ID={request_id}")

    print("[LIVE] ALL PASS: MySQL Audit Sink")

finally:
    if connection is not None:
        try:
            # 清理本次测试数据，不影响其他记录
            cleanup_cursor = connection.cursor()

            try:
                cleanup_cursor.execute(
                    """
                    DELETE FROM AGENT_AUDIT_LOG
                    WHERE REQUEST_ID = %s
                    """,
                    (request_id,),
                )

                connection.commit()

                print(
                    f"[LIVE] CLEANUP_ROWS="
                    f"{cleanup_cursor.rowcount}"
                )

            finally:
                cleanup_cursor.close()

        except Error:
            connection.rollback()
            print(
                "[LIVE] CLEANUP_FAILED: "
                "manual verification required"
            )
            raise

        finally:
            connection.close()
