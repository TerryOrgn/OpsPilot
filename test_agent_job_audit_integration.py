
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
        return [
            {
                "execution_id": f"EXEC-{i:03d}",
                "job_name": "MonthEndJob",
                "status": "FAILED",
                "updated_at": datetime(
                    2026, 10, 25, 12, 0
                ),
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

check(
    "AGENT_OK",
    response["ok"] is True,
)

check(
    "AUDIT_EXISTS",
    isinstance(response.get("audit"), dict),
)

audit = response["audit"]

check(
    "EVENT_NAME",
    audit["event"] == "JOB_MONITORING_SUMMARY",
)

check(
    "TOOL_NAME",
    audit["tool_name"] == "get_recent_abnormal_jobs",
)

check(
    "TOTAL_ABNORMAL",
    audit["total_abnormal_count"] == 15,
)

check(
    "RETURNED_COUNT",
    audit["returned_count"] == 10,
)

check(
    "TRUNCATED",
    audit["truncated"] is True,
)

check(
    "SUMMARY_STATUS",
    audit["summary_status"] == "SUCCESS",
)

check(
    "NO_JOB_DETAILS",
    "jobs" not in audit
    and "execution_id" not in audit
    and "job_name" not in audit,
)

check(
    "JSON_SERIALIZABLE",
    isinstance(json.dumps(audit), str),
)

check(
    "SUMMARY_STILL_EXISTS",
    "15条异常" in response["summary"]
    and "展示10条异常明细" in response["summary"],
)

check(
    "AUDIT_COUNTS_MATCH_TOOL",
    audit["total_abnormal_count"]
    == response["result"]["result"]["total_abnormal_count"]
    and audit["returned_count"]
    == response["result"]["result"]["returned_count"],
)

print(
    "[TEST] AUDIT=",
    json.dumps(audit, ensure_ascii=False),
)
print("[TEST] ALL PASS: Agent Job Audit Integration")
