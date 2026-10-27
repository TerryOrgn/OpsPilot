
import json

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


class FakeScheduler:

    def __init__(self):
        self.recovery_calls = 0

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


class FakeLLM:

    def __init__(self, decision=None, fail=False):
        self.decision = decision
        self.fail = fail
        self.calls = 0

    def decide(self, user_message):
        self.calls += 1

        if self.fail:
            raise RuntimeError("llm-secret")

        return self.decision


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


scheduler = FakeScheduler()
repository = FakeJobRepository()
llm = FakeLLM()

agent = OpsPilotMultiToolSafeAgent(
    scheduler=scheduler,
    job_repository=repository,
    llm=llm,
)


# 1. Direct answer
llm.decision = {
    "type": "DIRECT_ANSWER",
    "answer": "你好，我是 OpsPilot。",
}

direct = agent.ask("你好")

check(
    "DIRECT_ANSWER_SUCCESS",
    direct["ok"] is True,
)

check(
    "DIRECT_ANSWER_CONTENT",
    direct["answer"] == "你好，我是 OpsPilot。",
)


# 2. JOB tool routing
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": '{"limit": 2}',
}

jobs = agent.ask("最近有失败的 JOB 吗？")

check(
    "JOB_TOOL_ROUTED",
    jobs["ok"] is True,
)

check(
    "JOB_RESULT_COUNT",
    jobs["result"]["result"]["abnormal_count"] == 2,
)

check(
    "JOB_REPOSITORY_CALLED",
    repository.calls == 1,
)


# 3. Health tool routing
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "get_webhook_recovery_health",
    "arguments": "{}",
}

health = agent.ask(
    "Webhook Scheduler 健康吗？"
)

check(
    "HEALTH_TOOL_ROUTED",
    health["ok"] is True,
)

check(
    "HEALTH_TOOL_SELECTED",
    health["tool_name"]
    == "get_webhook_recovery_health",
)


# 4. Unknown tool
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "delete_all_jobs",
    "arguments": "{}",
}

unknown = agent.ask("删除所有 JOB")

check(
    "UNKNOWN_TOOL_REJECTED",
    unknown["result"]["error"]["code"]
    == "UNKNOWN_TOOL",
)


# 5. Invalid limit
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": '{"limit": 1000}',
}

invalid = agent.ask("查询 1000 条异常 JOB")

check(
    "INVALID_LIMIT_REJECTED",
    invalid["result"]["error"]["code"]
    == "INVALID_ARGUMENTS",
)


# 6. Invalid JSON
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": "{invalid",
}

malformed = agent.ask("查询异常 JOB")

check(
    "INVALID_JSON_REJECTED",
    malformed["result"]["error"]["code"]
    == "INVALID_JSON",
)


# 7. Invalid decision
llm.decision = {
    "type": "UNSUPPORTED_ACTION",
}

unsupported = agent.ask("执行操作")

check(
    "UNSUPPORTED_DECISION_REJECTED",
    unsupported["error"]["code"]
    == "INVALID_DECISION",
)


# 8. LLM exception
llm.fail = True

failed = agent.ask("查询状态")

check(
    "LLM_EXCEPTION_ISOLATED",
    failed["error"]["code"]
    == "LLM_DECISION_FAILED",
)

check(
    "LLM_SECRET_HIDDEN",
    "llm-secret" not in json.dumps(failed),
)

llm.fail = False


# 9. Empty message
calls_before = llm.calls

empty = agent.ask("   ")

check(
    "EMPTY_MESSAGE_REJECTED",
    empty["error"]["code"]
    == "INVALID_MESSAGE",
)

check(
    "EMPTY_MESSAGE_SKIPS_LLM",
    llm.calls == calls_before,
)


# 10. Invalid arguments type
llm.decision = {
    "type": "TOOL_CALL",
    "tool_name": "get_recent_abnormal_jobs",
    "arguments": {"limit": 2},
}

invalid_type = agent.ask("查询 JOB")

check(
    "NON_STRING_ARGUMENTS_REJECTED",
    invalid_type["error"]["code"]
    == "INVALID_DECISION",
)


# 11. Invalid direct answer
llm.decision = {
    "type": "DIRECT_ANSWER",
    "answer": 123,
}

bad_answer = agent.ask("你好")

check(
    "INVALID_ANSWER_REJECTED",
    bad_answer["error"]["code"]
    == "INVALID_DECISION",
)


# 12. Unexpected decision fields
llm.decision = {
    "type": "DIRECT_ANSWER",
    "answer": "OK",
    "execute": True,
}

extra_fields = agent.ask("你好")

check(
    "EXTRA_DECISION_FIELDS_REJECTED",
    extra_fields["error"]["code"]
    == "INVALID_DECISION",
)


# 13. Invalid decision object
llm.decision = ["TOOL_CALL"]

invalid_object = agent.ask("查询状态")

check(
    "NON_DICT_DECISION_REJECTED",
    invalid_object["error"]["code"]
    == "INVALID_DECISION",
)


# 14. Recovery never executed
check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)


# 15. JSON compatibility
json.dumps(direct)
json.dumps(jobs)
json.dumps(health)
json.dumps(unknown)

check(
    "RESULTS_JSON_COMPATIBLE",
    True,
)


# 16. Dependency validation
try:
    OpsPilotMultiToolSafeAgent(
        scheduler=scheduler,
        job_repository=repository,
        llm=None,
    )
except ValueError:
    missing_llm_rejected = True
else:
    missing_llm_rejected = False

check(
    "MISSING_LLM_REJECTED",
    missing_llm_rejected,
)


print(
    "[TEST] ALL PASS: "
    "OpsPilot Multi Tool Safe Agent"
)
