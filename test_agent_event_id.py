
from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
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


class FakeRecorder:
    def __init__(self):
        self.records = []

    def record(self, audit):
        self.records.append(dict(audit))
        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


recorder = FakeRecorder()

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=recorder,
)

first = agent.ask("检查异常JOB")
second = agent.ask("再次检查异常JOB")

check(
    "FIRST_REQUEST_OK",
    first["ok"] is True,
)

check(
    "SECOND_REQUEST_OK",
    second["ok"] is True,
)

first_id = first["audit"]["event_id"]
second_id = second["audit"]["event_id"]

check(
    "EVENT_ID_PRESENT",
    isinstance(first_id, str) and bool(first_id),
)

check(
    "EVENT_ID_WITHIN_64_CHARS",
    len(first_id) <= 64,
)

check(
    "DIFFERENT_EVENTS_DIFFERENT_IDS",
    first_id != second_id,
)

check(
    "FIRST_ID_PRESERVED_IN_RECORDER",
    recorder.records[0]["event_id"] == first_id,
)

check(
    "SECOND_ID_PRESERVED_IN_RECORDER",
    recorder.records[1]["event_id"] == second_id,
)

check(
    "RECORDING_SUCCESS",
    first["audit_recording_status"] == "SUCCESS"
    and second["audit_recording_status"] == "SUCCESS",
)

print("[TEST] ALL PASS: Agent Event ID")
