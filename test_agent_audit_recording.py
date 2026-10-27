
import json

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


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


class FakeRecorder:
    def __init__(self):
        self.records = []

    def record(self, audit):
        self.records.append(dict(audit))
        return True


class FailingRecorder:
    def record(self, audit):
        raise OSError("simulated audit failure")


def make_agent(recorder=None):
    return OpsPilotMultiToolSafeAgent(
        scheduler=FakeScheduler(),
        job_repository=FakeRepository(),
        llm=FakeLLM(),
        audit_recorder=recorder,
    )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


# Case 1: Recorder success
recorder = FakeRecorder()
agent = make_agent(recorder)
response = agent.ask("检查异常JOB")

check(
    "JOB_SUCCESS",
    response["ok"] is True,
)

check(
    "AUDIT_RECORDING_SUCCESS",
    response.get("audit_recording_status") == "SUCCESS",
)

check(
    "RECORDER_CALLED_ONCE",
    len(recorder.records) == 1,
)

check(
    "RECORDED_AUDIT_MATCHES",
    recorder.records[0] == response["audit"],
)


# Case 2: Recorder failure
agent = make_agent(FailingRecorder())
response = agent.ask("检查异常JOB")

check(
    "JOB_SURVIVES_AUDIT_FAILURE",
    response["ok"] is True,
)

check(
    "AUDIT_RECORDING_FAILED",
    response.get("audit_recording_status") == "FAILED",
)

check(
    "SUMMARY_SURVIVES_AUDIT_FAILURE",
    "summary" in response,
)

check(
    "AUDIT_SURVIVES_AUDIT_FAILURE",
    "audit" in response,
)


# Case 3: No Recorder configured
agent = make_agent()
response = agent.ask("检查异常JOB")

check(
    "NO_RECORDER_JOB_SUCCESS",
    response["ok"] is True,
)

check(
    "NO_RECORDER_STATUS_ABSENT",
    "audit_recording_status" not in response,
)

check(
    "NO_RECORDER_AUDIT_PRESENT",
    "audit" in response,
)

print("[TEST] ALL PASS: Agent Audit Recording")
