
import uuid

from opspilot_multi_tool_safe_agent import OpsPilotMultiToolSafeAgent
from job_audit_recorder import JobAuditRecorder
from mysql_audit_sink import MySQLAuditSink
from webhook_notification_recovery_trace_context import (
    get_request_id,
    set_request_id,
    reset_request_id,
)


def failing_connection_factory():
    raise ConnectionError("Simulated MySQL connection failure")


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


request_id = "REQ-BO3-" + uuid.uuid4().hex[:16]

sink = MySQLAuditSink(
    connection_factory=failing_connection_factory
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

    check(
        "AUDIT_RECORDING_FAILED",
        response.get("audit_recording_status") == "FAILED",
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

print(f"[TEST] REQUEST_ID={request_id}")
print("[TEST] ALL PASS: Audit MySQL Failure Isolation")
