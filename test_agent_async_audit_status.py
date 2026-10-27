
from audit_task_queue import BoundedAuditQueue
from audit_queue_adapter import AuditQueueAdapter
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


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def create_agent(recorder):
    return OpsPilotMultiToolSafeAgent(
        scheduler=FakeScheduler(),
        job_repository=FakeRepository(),
        llm=FakeLLM(),
        audit_recorder=recorder,
    )


# 场景一：正常入队
audit_queue = BoundedAuditQueue(maxsize=1)
agent = create_agent(AuditQueueAdapter(audit_queue))

response = agent.ask("查询最近异常 JOB")

check(
    "BUSINESS_SUCCESS",
    response["ok"] is True,
)

check(
    "AUDIT_QUEUED",
    response["audit_recording_status"] == "QUEUED",
)

check(
    "QUEUE_HAS_ONE_ITEM",
    audit_queue.size() == 1,
)

check(
    "EVENT_ID_PRESERVED",
    bool(response["audit"]["event_id"]),
)


# 场景二：队列已满
response2 = agent.ask("再次查询最近异常 JOB")

check(
    "BUSINESS_SUCCESS_WHEN_FULL",
    response2["ok"] is True,
)

check(
    "AUDIT_REJECTED_WHEN_FULL",
    response2["audit_recording_status"]
    == "REJECTED",
)

check(
    "QUEUE_CAPACITY_PRESERVED",
    audit_queue.size() == 1,
)


# 场景三：同步 Recorder 兼容性
class SyncRecorder:
    def record(self, audit):
        return True


agent = create_agent(SyncRecorder())
response3 = agent.ask("查询最近异常 JOB")

check(
    "SYNC_RECORDER_SUCCESS",
    response3["audit_recording_status"]
    == "SUCCESS",
)


# 场景四：审计异常隔离
class FailedRecorder:
    def record(self, audit):
        raise RuntimeError("Audit failure")


agent = create_agent(FailedRecorder())
response4 = agent.ask("查询最近异常 JOB")

check(
    "AUDIT_EXCEPTION_FAILED",
    response4["audit_recording_status"]
    == "FAILED",
)

check(
    "BUSINESS_UNAFFECTED",
    response4["ok"] is True,
)

print("[TEST] ALL PASS: Agent Async Audit Status")
