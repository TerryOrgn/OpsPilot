
import json

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)
from job_audit_recorder import JobAuditRecorder
from webhook_notification_recovery_trace_context import set_request_id, get_request_id, reset_request_id


class FakeLLM:
    def decide(self, message):
        return {
            "type": "TOOL_CALL",
            "tool_name": "get_recent_abnormal_jobs",
            "arguments": json.dumps({"limit": 10}),
        }


class FakeRepository:
    def get_recent_jobs(self):
        return []


class FakeScheduler:
    pass


class FakeSink:
    def __init__(self):
        self.records = []

    def write(self, payload):
        self.records.append(payload)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


sink = FakeSink()
recorder = JobAuditRecorder(sink)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=recorder,
)

original_id = get_request_id()

token = set_request_id("REQ-BN3D-001")

try:
    response = agent.ask("检查异常JOB")

    check(
        "AGENT_SUCCESS",
        response["ok"] is True,
    )

    check(
        "AUDIT_REQUEST_ID",
        response["audit"].get("request_id")
        == "REQ-BN3D-001",
    )

    check(
        "RECORDING_SUCCESS",
        response.get("audit_recording_status")
        == "SUCCESS",
    )

    check(
        "SINK_RECEIVED_ONCE",
        len(sink.records) == 1,
    )

    saved = json.loads(sink.records[0])

    check(
        "SINK_REQUEST_ID_MATCHES",
        saved["request_id"] == "REQ-BN3D-001",
    )

    check(
        "AUDIT_MATCHES_SINK",
        saved == response["audit"],
    )

    check(
        "CONTEXT_UNCHANGED_DURING_ASK",
        get_request_id() == "REQ-BN3D-001",
    )

finally:
    reset_request_id(token)


check(
    "CONTEXT_RESTORED",
    get_request_id() == original_id,
)

print("[TEST] ALL PASS: Agent Audit Request ID Integration")
