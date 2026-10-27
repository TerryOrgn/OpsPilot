
import json

from opspilot_multi_tool_safe_agent import OpsPilotMultiToolSafeAgent
from job_audit_recorder import JobAuditRecorder
from webhook_notification_recovery_trace_context import get_request_id, set_request_id, reset_request_id


# 复制 BN-3D 已验证成功的实际导入语句
# from your_actual_module import (
#     get_request_id, set_request_id, reset_request_id
# )


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

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=JobAuditRecorder(sink),
)

original_id = get_request_id()


def run_request(request_id):
    token = set_request_id(request_id)
    try:
        return agent.ask("检查异常JOB")
    finally:
        reset_request_id(token)


response_a = run_request("REQ-BN3E-A")
response_b = run_request("REQ-BN3E-B")

check(
    "REQUEST_A_SUCCESS",
    response_a["ok"] is True,
)

check(
    "REQUEST_B_SUCCESS",
    response_b["ok"] is True,
)

check(
    "REQUEST_A_ID",
    response_a["audit"]["request_id"] == "REQ-BN3E-A",
)

check(
    "REQUEST_B_ID",
    response_b["audit"]["request_id"] == "REQ-BN3E-B",
)

check(
    "REQUEST_IDS_DIFFERENT",
    response_a["audit"]["request_id"]
    != response_b["audit"]["request_id"],
)

saved = [json.loads(item) for item in sink.records]

check(
    "TWO_AUDIT_RECORDS",
    len(saved) == 2,
)

check(
    "SINK_IDS_CORRECT",
    [item["request_id"] for item in saved]
    == ["REQ-BN3E-A", "REQ-BN3E-B"],
)

check(
    "RECORDING_SUCCESS",
    response_a["audit_recording_status"] == "SUCCESS"
    and response_b["audit_recording_status"] == "SUCCESS",
)

check(
    "CONTEXT_RESTORED",
    get_request_id() == original_id,
)

print("[TEST] ALL PASS: Agent Audit Request Isolation")
