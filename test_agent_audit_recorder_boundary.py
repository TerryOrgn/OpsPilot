
import json
from unittest.mock import patch

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


class FakeLLM:
    def __init__(self, decision):
        self.decision = decision

    def decide(self, message):
        return self.decision


class FakeRepository:
    def get_recent_jobs(self):
        return []


class FakeScheduler:
    pass


class SpyRecorder:
    def __init__(self):
        self.calls = []

    def record(self, audit):
        self.calls.append(dict(audit))
        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def tool_decision(name, arguments):
    return {
        "type": "TOOL_CALL",
        "tool_name": name,
        "arguments": json.dumps(arguments),
    }


def make_agent(decision, recorder):
    return OpsPilotMultiToolSafeAgent(
        scheduler=FakeScheduler(),
        job_repository=FakeRepository(),
        llm=FakeLLM(decision),
        audit_recorder=recorder,
    )


# Case 1: Direct answer
recorder = SpyRecorder()
agent = make_agent(
    {"type": "DIRECT_ANSWER", "answer": "你好"},
    recorder,
)
response = agent.ask("你好")

check(
    "DIRECT_ANSWER_NO_RECORD",
    response["ok"] is True
    and len(recorder.calls) == 0,
)


# Case 2: Unknown tool
recorder = SpyRecorder()
agent = make_agent(
    tool_decision("unknown_tool", {}),
    recorder,
)
response = agent.ask("未知工具")

check(
    "UNKNOWN_TOOL_NO_RECORD",
    response["ok"] is False
    and len(recorder.calls) == 0,
)


# Case 3: Invalid JOB limit
recorder = SpyRecorder()
agent = make_agent(
    tool_decision(
        "get_recent_abnormal_jobs",
        {"limit": 0},
    ),
    recorder,
)
response = agent.ask("检查JOB")

check(
    "INVALID_LIMIT_NO_RECORD",
    response["ok"] is False
    and len(recorder.calls) == 0,
)


# Case 4: Health tool
recorder = SpyRecorder()
agent = make_agent(
    tool_decision(
        "get_webhook_notification_recovery_health",
        {},
    ),
    recorder,
)

with patch.object(
    agent._dispatcher,
    "dispatch",
    return_value={
        "ok": True,
        "tool_name": "get_webhook_notification_recovery_health",
        "result": {"status": "HEALTHY"},
    },
):
    response = agent.ask("检查健康状态")

check(
    "HEALTH_TOOL_NO_RECORD",
    response["ok"] is True
    and len(recorder.calls) == 0,
)


# Case 5: Invalid JOB metadata
recorder = SpyRecorder()
agent = make_agent(
    tool_decision(
        "get_recent_abnormal_jobs",
        {"limit": 10},
    ),
    recorder,
)

with patch.object(
    agent._dispatcher,
    "dispatch",
    return_value={
        "ok": True,
        "tool_name": "get_recent_abnormal_jobs",
        "result": {
            "schema_version": "1.1",
            "tool_name": "get_recent_abnormal_jobs",
            "abnormal_count": 2,
            "total_abnormal_count": 1,
            "returned_count": 2,
            "truncated": False,
            "jobs": [{}, {}],
        },
    },
):
    response = agent.ask("检查JOB")

check(
    "INVALID_METADATA_NO_RECORD",
    response["ok"] is False
    and len(recorder.calls) == 0,
)

check(
    "INVALID_METADATA_NO_RECORDING_STATUS",
    "audit_recording_status" not in response,
)


# Case 6: Valid JOB result with zero abnormalities
recorder = SpyRecorder()
agent = make_agent(
    tool_decision(
        "get_recent_abnormal_jobs",
        {"limit": 10},
    ),
    recorder,
)
response = agent.ask("检查JOB")

check(
    "ZERO_ABNORMAL_JOB_SUCCESS",
    response["ok"] is True,
)

check(
    "ZERO_ABNORMAL_RECORDED",
    len(recorder.calls) == 1
    and recorder.calls[0]["total_abnormal_count"] == 0
    and recorder.calls[0]["returned_count"] == 0
    and recorder.calls[0]["truncated"] is False,
)

check(
    "ZERO_ABNORMAL_RECORDING_SUCCESS",
    response.get("audit_recording_status") == "SUCCESS",
)

print("[TEST] ALL PASS: Agent Audit Recorder Boundary")
