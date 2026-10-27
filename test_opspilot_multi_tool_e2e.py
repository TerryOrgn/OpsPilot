
import json
from types import SimpleNamespace

from opspilot_multi_tool_llm_decision import (
    OpsPilotMultiToolLLMDecision,
)
from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


JOB_TOOL = "get_recent_abnormal_jobs"
HEALTH_TOOL = "get_webhook_recovery_health"


class FakeResponses:

    def __init__(self):
        self.response = None
        self.calls = 0
        self.last_request = None

    def create(self, **kwargs):
        self.calls += 1
        self.last_request = kwargs

        if self.response is None:
            raise RuntimeError("fake-api-not-configured")

        return self.response


class FakeClient:

    def __init__(self):
        self.responses = FakeResponses()


class FakeScheduler:

    def __init__(self):
        self.health_calls = 0
        self.recovery_calls = 0

    def get_health_snapshot(self):
        self.health_calls += 1

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

    def run_once(self):
        self.recovery_calls += 1
        raise AssertionError(
            "Recovery execution is forbidden"
        )


class FakeJobRepository:

    def __init__(self):
        self.calls = 0

    def get_recent_jobs(self):
        self.calls += 1

        return [
            {
                "execution_id": "EXEC-003",
                "job_name": "MONTH_END",
                "status": "FAILED",
                "updated_at": "2026-10-24T10:03:00",
            },
            {
                "execution_id": "EXEC-002",
                "job_name": "DAILY_SYNC",
                "status": "SUCCESS",
                "updated_at": "2026-10-24T10:02:00",
            },
            {
                "execution_id": "EXEC-001",
                "job_name": "DATA_IMPORT",
                "status": "TIMEOUT",
                "updated_at": "2026-10-24T10:01:00",
            },
        ]


def make_call(name, arguments):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=arguments,
    )


def make_response(output=None, output_text=""):
    return SimpleNamespace(
        output=[] if output is None else output,
        output_text=output_text,
    )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


client = FakeClient()
scheduler = FakeScheduler()
repository = FakeJobRepository()

llm = OpsPilotMultiToolLLMDecision(
    client=client,
    model="fake-model",
)

agent = OpsPilotMultiToolSafeAgent(
    scheduler=scheduler,
    job_repository=repository,
    llm=llm,
)


# 1. JOB monitoring end-to-end
client.responses.response = make_response(
    output=[
        make_call(JOB_TOOL, '{"limit": 2}')
    ]
)

job_result = agent.ask("最近有失败的 JOB 吗？")

check(
    "JOB_E2E_SUCCESS",
    job_result["ok"] is True,
)

check(
    "JOB_TOOL_SELECTED",
    job_result["tool_name"] == JOB_TOOL,
)

job_data = job_result["result"]["result"]

check(
    "JOB_ABNORMAL_COUNT",
    job_data["abnormal_count"] == 2,
)

check(
    "JOB_STATUSES_CORRECT",
    [j["status"] for j in job_data["jobs"]]
    == ["FAILED", "TIMEOUT"],
)

check(
    "JOB_REPOSITORY_CALLED_ONCE",
    repository.calls == 1,
)


# 2. Webhook health end-to-end
client.responses.response = make_response(
    output=[
        make_call(HEALTH_TOOL, "{}")
    ]
)

health_result = agent.ask(
    "Webhook Scheduler 健康吗？"
)

check(
    "HEALTH_E2E_SUCCESS",
    health_result["ok"] is True,
)

check(
    "HEALTH_TOOL_SELECTED",
    health_result["tool_name"] == HEALTH_TOOL,
)

check(
    "HEALTH_SCHEDULER_CALLED_ONCE",
    scheduler.health_calls == 1,
)


# 3. Direct answer
client.responses.response = make_response(
    output=[],
    output_text="你好，我是 OpsPilot。",
)

calls_before = repository.calls

direct_result = agent.ask("你好")

check(
    "DIRECT_ANSWER_SUCCESS",
    direct_result["ok"] is True,
)

check(
    "DIRECT_ANSWER_CONTENT",
    direct_result["answer"]
    == "你好，我是 OpsPilot。",
)

check(
    "DIRECT_ANSWER_SKIPS_REPOSITORY",
    repository.calls == calls_before,
)


# 4. Unknown tool must be rejected
client.responses.response = make_response(
    output=[
        make_call("delete_all_jobs", "{}")
    ]
)

unknown_result = agent.ask("删除所有 JOB")

check(
    "UNKNOWN_TOOL_REJECTED",
    unknown_result["result"]["error"]["code"]
    == "UNKNOWN_TOOL",
)


# 5. Invalid limit must be rejected
client.responses.response = make_response(
    output=[
        make_call(JOB_TOOL, '{"limit": 1000}')
    ]
)

invalid_result = agent.ask(
    "查询 1000 条异常 JOB"
)

check(
    "INVALID_LIMIT_REJECTED",
    invalid_result["result"]["error"]["code"]
    == "INVALID_ARGUMENTS",
)


# 6. Multiple tool calls must be rejected
client.responses.response = make_response(
    output=[
        make_call(JOB_TOOL, '{"limit": 2}'),
        make_call(HEALTH_TOOL, "{}"),
    ]
)

multiple_result = agent.ask("查询全部状态")

check(
    "MULTIPLE_CALLS_REJECTED",
    multiple_result["error"]["code"]
    == "LLM_DECISION_FAILED",
)


# 7. Fake API exception isolation
client.responses.response = None

api_error = agent.ask("查询 JOB")

check(
    "API_EXCEPTION_ISOLATED",
    api_error["error"]["code"]
    == "LLM_DECISION_FAILED",
)

check(
    "API_ERROR_DETAIL_HIDDEN",
    "fake-api-not-configured"
    not in json.dumps(api_error),
)


# 8. Read-only boundary
check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)


# 9. Tool definitions sent to API
request = client.responses.last_request

check(
    "TWO_TOOLS_SENT",
    len(request["tools"]) == 2,
)

check(
    "PARALLEL_CALLS_DISABLED",
    request["parallel_tool_calls"] is False,
)


# 10. JSON compatibility
json.dumps(job_result)
json.dumps(health_result)
json.dumps(direct_result)

check(
    "RESULTS_JSON_COMPATIBLE",
    True,
)


print(
    "[TEST] ALL PASS: "
    "OpsPilot Multi Tool E2E"
)
