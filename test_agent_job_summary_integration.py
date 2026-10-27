
import json
from datetime import datetime

from opspilot_multi_tool_safe_agent import (
    OpsPilotMultiToolSafeAgent,
)


class FakeLLM:
    def decide(self, user_message):
        return {
            "type": "TOOL_CALL",
            "tool_name": "get_recent_abnormal_jobs",
            "arguments": json.dumps({"limit": 10}),
        }


class FakeRepository:
    def get_recent_jobs(self):
        now = datetime(2026, 10, 25, 12, 0)

        return [
            {
                "execution_id": f"EXEC-{i:03d}",
                "job_name": "MonthEndJob",
                "status": "FAILED",
                "updated_at": now,
            }
            for i in range(15)
        ]


class FakeScheduler:
    pass


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
)

response = agent.ask("检查最近的异常JOB")

tool_result = response["result"]["result"]

check("AGENT_OK", response["ok"] is True)
check("TOOL_RESULT", response["type"] == "TOOL_RESULT")
check("SCHEMA_VERSION", tool_result["schema_version"] == "1.1")
check("TOTAL_ABNORMAL", tool_result["total_abnormal_count"] == 15)
check("RETURNED_COUNT", tool_result["returned_count"] == 10)
check("TRUNCATED", tool_result["truncated"] is True)
check("SUMMARY_EXISTS", isinstance(response.get("summary"), str))
check("SUMMARY_TOTAL", "15条异常" in response["summary"])
check("SUMMARY_RETURNED", "展示10条异常明细" in response["summary"])
check("SUMMARY_MISSING", "还有5条异常未展示明细" in response["summary"])

print("[TEST] SUMMARY=", response["summary"])
print("[TEST] ALL PASS: Agent Job Summary Integration")
