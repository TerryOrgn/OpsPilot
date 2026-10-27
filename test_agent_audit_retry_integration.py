
from audit_retry_service import AuditRetryService
from audit_retry_adapter import AuditRetryAdapter
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
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    def record(self, audit):
        self.calls.append(dict(audit))

        if self.should_fail:
            raise ConnectionError(
                "Simulated database failure"
            )

        return True


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def create_agent(recorder):
    retry_service = AuditRetryService(
        recorder=recorder,
        max_attempts=2,
        sleep_fn=lambda seconds: None,
    )

    adapter = AuditRetryAdapter(retry_service)

    return OpsPilotMultiToolSafeAgent(
        scheduler=FakeScheduler(),
        job_repository=FakeRepository(),
        llm=FakeLLM(),
        audit_recorder=adapter,
    )


# 场景一：审计写入成功
success_recorder = FakeRecorder()
agent = create_agent(success_recorder)

success_response = agent.ask(
    "查询最近异常 JOB"
)

check(
    "BUSINESS_SUCCESS",
    success_response["ok"] is True,
)

check(
    "AUDIT_SUCCESS",
    success_response["audit_recording_status"]
    == "SUCCESS",
)

check(
    "SUCCESS_ONE_WRITE",
    len(success_recorder.calls) == 1,
)


# 场景二：审计数据库持续故障
failed_recorder = FakeRecorder(should_fail=True)
agent = create_agent(failed_recorder)

failed_response = agent.ask(
    "查询最近异常 JOB"
)

check(
    "BUSINESS_STILL_SUCCESS",
    failed_response["ok"] is True,
)

check(
    "AUDIT_FAILED",
    failed_response["audit_recording_status"]
    == "FAILED",
)

check(
    "TWO_RETRY_ATTEMPTS",
    len(failed_recorder.calls) == 2,
)

check(
    "SAME_EVENT_ID_ON_RETRY",
    failed_recorder.calls[0]["event_id"]
    == failed_recorder.calls[1]["event_id"],
)

check(
    "SUMMARY_PRESERVED",
    isinstance(failed_response["summary"], str)
    and bool(failed_response["summary"]),
)

check(
    "AUDIT_PRESERVED",
    isinstance(failed_response["audit"], dict)
    and bool(failed_response["audit"]["event_id"]),
)

print(
    "[TEST] ALL PASS: Agent Audit Retry Integration"
)
