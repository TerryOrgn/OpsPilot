
import uuid

from opspilot_multi_tool_safe_agent import OpsPilotMultiToolSafeAgent
from job_audit_recorder import JobAuditRecorder
from mysql_audit_sink import MySQLAuditSink
from webhook_notification_recovery_trace_context import (
    get_request_id,
    set_request_id,
    reset_request_id,
)


class FakeCursor:
    def __init__(self):
        self.execute_called = False
        self.close_called = False

    def execute(self, sql, params):
        self.execute_called = True

    def close(self):
        self.close_called = True


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.commit_called = False
        self.rollback_called = False
        self.close_called = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_called = True
        raise RuntimeError("Simulated MySQL commit failure")

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


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
    print(f"[TEST] {name}=PASS")


connection = FakeConnection()

sink = MySQLAuditSink(
    connection_factory=lambda: connection
)

recorder = JobAuditRecorder(sink)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=recorder,
)

request_id = "REQ-BO4-" + uuid.uuid4().hex[:16]

original_id = get_request_id()
token = set_request_id(request_id)

try:
    response = agent.ask("检查异常JOB")

    check(
        "AGENT_SUCCESS",
        response["ok"] is True,
    )

    check(
        "AUDIT_RECORDING_FAILED",
        response.get("audit_recording_status") == "FAILED",
    )

    check(
        "REQUEST_ID_MATCH",
        response["audit"]["request_id"] == request_id,
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

check(
    "SQL_EXECUTED",
    connection.cursor_instance.execute_called,
)

check(
    "COMMIT_ATTEMPTED",
    connection.commit_called,
)

check(
    "ROLLBACK_CALLED",
    connection.rollback_called,
)

check(
    "CURSOR_CLOSED",
    connection.cursor_instance.close_called,
)

check(
    "CONNECTION_CLOSED",
    connection.close_called,
)

print(f"[TEST] REQUEST_ID={request_id}")
print("[TEST] ALL PASS: Audit Commit Failure Isolation")
