
import os
import uuid
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)
from job_audit_recorder import JobAuditRecorder
from mysql_audit_sink import MySQLAuditSink
from webhook_notification_recovery_trace_context import (
    get_request_id,
    set_request_id,
    reset_request_id,
)


load_dotenv(
    dotenv_path=Path(__file__).resolve().parent / ".env"
)


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


request_id = "REQ-BO5F-" + uuid.uuid4().hex[:16]

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

responses = []

try:
    # 两次独立的 Agent 调用
    first = agent.ask("第一次检查异常JOB")
    second = agent.ask("第二次检查异常JOB")

    responses = [first, second]

    check(
        "BOTH_AGENT_CALLS_OK",
        all(r["ok"] is True for r in responses),
    )

    check(
        "BOTH_AUDITS_PRESENT",
        all("audit" in r for r in responses),
    )

    check(
        "BOTH_RECORDINGS_SUCCESS",
        all(
            r.get("audit_recording_status") == "SUCCESS"
            for r in responses
        ),
    )

    first_id = first["audit"]["event_id"]
    second_id = second["audit"]["event_id"]

    check(
        "EVENT_IDS_DISTINCT",
        first_id != second_id,
    )

    check(
        "REQUEST_IDS_MATCH",
        all(
            r["audit"]["request_id"] == request_id
            for r in responses
        ),
    )

    # 同一审计事件重试：复用原有 Event ID
    recorder.record(first["audit"])

    check(
        "DUPLICATE_WRITE_ACCEPTED",
        True,
    )

finally:
    reset_request_id(token)


check(
    "CONTEXT_RESTORED",
    get_request_id() == original_id,
)


# 使用独立连接查询真实 MySQL
connection = create_connection()

try:
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                EVENT_ID,
                REQUEST_ID,
                EVENT,
                TOOL_NAME
            FROM AGENT_AUDIT_LOG
            WHERE REQUEST_ID = %s
            """,
            (request_id,),
        )

        rows = cursor.fetchall()

    finally:
        cursor.close()

    check(
        "MYSQL_EXACTLY_TWO_ROWS",
        len(rows) == 2,
    )

    saved_ids = {row["EVENT_ID"] for row in rows}
    expected_ids = {
        responses[0]["audit"]["event_id"],
        responses[1]["audit"]["event_id"],
    }

    check(
        "MYSQL_EVENT_IDS_MATCH",
        saved_ids == expected_ids,
    )

    check(
        "MYSQL_REQUEST_IDS_MATCH",
        all(row["REQUEST_ID"] == request_id for row in rows),
    )

    check(
        "MYSQL_EVENT_FIELDS_MATCH",
        all(
            row["EVENT"] == "JOB_MONITORING_SUMMARY"
            and row["TOOL_NAME"] == "get_recent_abnormal_jobs"
            for row in rows
        ),
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
print("[LIVE] ALL PASS: Agent Event ID MySQL Integration")
