
import os
import uuid

import mysql.connector

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(
    dotenv_path=Path(__file__).resolve().parent / ".env"
)

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)
from job_audit_recorder import JobAuditRecorder
from mysql_audit_sink import MySQLAuditSink
from webhook_notification_recovery_trace_context import get_request_id, set_request_id, reset_request_id


# 复制 BN-4A 已验证通过的 Request Context 导入语句
# from 实际模块名 import (
#     get_request_id, set_request_id, reset_request_id
# )

# 如果 BO-2B 使用 .env，请保留相同的加载方式。
# 例如：
# from dotenv import load_dotenv
# load_dotenv()


def create_connection():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=5,
    )


class FakeLLM:
    def decide(self, message):
        return {
            "type": "TOOL_CALL",
            "tool_name": "get_recent_abnormal_jobs",
            "arguments": '{"limit": 10}',
        }


class FakeRepository:
    def get_recent_jobs(self):
        return []


class FakeScheduler:
    pass


def check(name, condition):
    assert condition, name
    print(f"[LIVE] {name}=PASS")


request_id = "REQ-BO2C-" + uuid.uuid4().hex[:16]

sink = MySQLAuditSink(
    connection_factory=create_connection
)

recorder = JobAuditRecorder(sink)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=recorder,
)

original_id = get_request_id()
token = set_request_id(request_id)

try:
    # 1. 执行 Agent
    response = agent.ask("检查异常JOB")

    check(
        "AGENT_SUCCESS",
        response["ok"] is True,
    )

    check(
        "AUDIT_EXISTS",
        "audit" in response,
    )

    check(
        "AUDIT_REQUEST_ID",
        response["audit"]["request_id"] == request_id,
    )

    print(
        "[DEBUG] AUDIT_RECORDING_STATUS=",
        response.get("audit_recording_status")
    )

    if response.get("audit_recording_status") != "SUCCESS":
        print("[DEBUG] AUDIT=", repr(response.get("audit")))

        try:
            recorder.record(response["audit"])
            print("[DEBUG] DIRECT_RECORDER=PASS")
        except Exception as exc:
            print("[DEBUG] DIRECT_RECORDER=FAILED")
            print("[DEBUG] ERROR_TYPE=", type(exc).__name__)
            print("[DEBUG] ERROR_MESSAGE=", str(exc))

    check(
        "AUDIT_RECORDING_SUCCESS",
        response.get("audit_recording_status") == "SUCCESS",
    )

    check(
        "SUMMARY_EXISTS",
        "summary" in response,
    )

finally:
    reset_request_id(token)


check(
    "CONTEXT_RESTORED",
    get_request_id() == original_id,
)


# 2. 使用独立连接查询数据库
connection = create_connection()

try:
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
        "MYSQL_RECORD_FOUND",
        len(rows) == 1,
    )

    saved = rows[0]

    check(
        "MYSQL_REQUEST_ID_MATCH",
        saved["REQUEST_ID"] == request_id,
    )

    check(
        "MYSQL_EVENT_MATCH",
        saved["EVENT"] == response["audit"]["event"],
    )

    check(
        "MYSQL_COUNTS_MATCH",
        saved["TOTAL_ABNORMAL_COUNT"]
        == response["audit"]["total_abnormal_count"]
        and saved["RETURNED_COUNT"]
        == response["audit"]["returned_count"],
    )

    check(
        "MYSQL_CREATED_AT",
        saved["CREATED_AT"] is not None,
    )

finally:
    try:
        cleanup_cursor = connection.cursor()

        try:
            cleanup_cursor.execute(
                """
                DELETE FROM AGENT_AUDIT_LOG
                WHERE REQUEST_ID = %s
                """,
                (request_id,),
            )

            deleted = cleanup_cursor.rowcount
            connection.commit()

            print(f"[LIVE] CLEANUP_ROWS={deleted}")

        finally:
            cleanup_cursor.close()

    finally:
        connection.close()


print(f"[LIVE] REQUEST_ID={request_id}")
print("[LIVE] ALL PASS: Agent MySQL Audit Integration")
