
from datetime import datetime, timedelta
from types import SimpleNamespace

from opspilot_multi_tool_llm_decision import (
    OpsPilotMultiToolLLMDecision,
)
from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


NOW = datetime(2026, 10, 24, 12, 0, 0)
JOB_TOOL = "get_recent_abnormal_jobs"


class FakeResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name=JOB_TOOL,
                    arguments='{"limit": 10}',
                )
            ],
            output_text="",
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


class FakeScheduler:
    def get_health_snapshot(self):
        return {
            "scheduler_health": "HEALTHY",
            "health_reason": "OK",
            "recovery_status": "NOT_RUN",
            "ready_for_recovery": True,
            "readiness_reason": "READY",
            "total_runs": 0,
            "consecutive_failures": 0,
            "last_success_time": None,
        }


class FakeRepository:
    def __init__(self):
        self.calls = 0
        self.jobs = [
            {
                "execution_id": "EXEC-001",
                "job_name": "RunningTimeout",
                "status": "RUNNING",
                "updated_at": NOW - timedelta(minutes=60),
            },
            {
                "execution_id": "EXEC-002",
                "job_name": "RunningNormal",
                "status": "RUNNING",
                "updated_at": NOW - timedelta(minutes=10),
            },
            {
                "execution_id": "EXEC-003",
                "job_name": "FailedJob",
                "status": "FAILED",
                "updated_at": NOW - timedelta(minutes=20),
            },
            {
                "execution_id": "EXEC-004",
                "job_name": "SuccessJob",
                "status": "SUCCESS",
                "updated_at": NOW - timedelta(minutes=5),
            },
        ]

    def get_recent_jobs(self):
        self.calls += 1
        return self.jobs


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


repository = FakeRepository()
client = FakeClient()

llm = OpsPilotMultiToolLLMDecision(
    client=client,
    model="fake-model",
)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=repository,
    llm=llm,
    enable_job_timeout_detection=True,
    now_provider=lambda: NOW,
)

response = agent.ask("最近有哪些异常 JOB？")

check(
    "AGENT_SUCCESS",
    response["ok"] is True,
)

check(
    "TOOL_RESULT_RETURNED",
    response["type"] == "TOOL_RESULT",
)

check(
    "JOB_TOOL_SELECTED",
    response["tool_name"] == JOB_TOOL,
)

data = response["result"]["result"]
jobs = data["jobs"]
print("[DEBUG] JOB_RESULT=", repr(data))

check(
    "ABNORMAL_COUNT",
    data["abnormal_count"] == 2,
)

check(
    "RUNNING_TIMEOUT_INCLUDED",
    jobs[0]["status"] == "TIMEOUT",
)

check(
    "ORIGINAL_RUNNING_PRESERVED",
    jobs[0]["original_status"] == "RUNNING",
)

check(
    "FAILED_INCLUDED",
    jobs[1]["status"] == "FAILED",
)

check(
    "NORMAL_RUNNING_EXCLUDED",
    all(
        job["execution_id"] != "EXEC-002"
        for job in jobs
    ),
)

check(
    "SUCCESS_EXCLUDED",
    all(
        job["execution_id"] != "EXEC-004"
        for job in jobs
    ),
)

check(
    "REPOSITORY_CALLED_ONCE",
    repository.calls == 1,
)

check(
    "LLM_CALLED_ONCE",
    client.responses.calls == 1,
)

check(
    "DATABASE_STATE_UNCHANGED",
    repository.jobs[0]["status"] == "RUNNING",
)


# Legacy mode remains unchanged.
legacy_repository = FakeRepository()
legacy_client = FakeClient()

legacy_agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=legacy_repository,
    llm=OpsPilotMultiToolLLMDecision(
        client=legacy_client,
        model="fake-model",
    ),
    now_provider=lambda: NOW,
)

legacy_response = legacy_agent.ask(
    "最近有哪些异常 JOB？"
)

legacy_data = legacy_response["result"]["result"]

check(
    "LEGACY_ABNORMAL_COUNT",
    legacy_data["abnormal_count"] == 1,
)

check(
    "LEGACY_RUNNING_EXCLUDED",
    all(
        job["status"] != "RUNNING"
        for job in legacy_data["jobs"]
    ),
)

print(
    "[TEST] ALL PASS: "
    "OpsPilot Agent Timeout Integration"
)
