
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


class FailingRecorder:
    def __init__(self):
        self.attempted_audit = None
        self.call_count = 0

    def record(self, audit):
        self.call_count += 1
        self.attempted_audit = dict(audit)

        raise ConnectionError(
            "Simulated audit database unavailable"
        )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


recorder = FailingRecorder()

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=recorder,
)

response = agent.ask("检查异常JOB")

# 1. JOB 工具调用仍然成功
check(
    "AGENT_RESULT_OK",
    response["ok"] is True,
)

# 2. 审计写入失败被正确隔离
check(
    "AUDIT_RECORDING_FAILED",
    response.get("audit_recording_status") == "FAILED",
)

# 3. Agent 响应仍包含审计事件
check(
    "AUDIT_PRESENT",
    isinstance(response.get("audit"), dict),
)

# 4. Event ID 未丢失
event_id = response["audit"].get("event_id")

check(
    "EVENT_ID_PRESERVED",
    isinstance(event_id, str)
    and bool(event_id.strip())
    and len(event_id) <= 64,
)

# 5. 失败写入时使用的 Event ID
#    与 Agent 返回的 Event ID 一致
check(
    "FAILED_ATTEMPT_ID_MATCH",
    recorder.attempted_audit["event_id"] == event_id,
)

# 6. Recorder 只调用了一次
check(
    "RECORDER_CALLED_ONCE",
    recorder.call_count == 1,
)

print("[DEBUG] SUMMARY_TYPE=", type(response.get("summary")).__name__)
print("[DEBUG] SUMMARY_VALUE=", repr(response.get("summary")))

# 7. 业务摘要没有受到审计失败影响
check(
    "SUMMARY_PRESERVED",
    "summary" in response
    and response["summary"] is not None,
)

# 8. 工具执行结果仍然保留
check(
    "TOOL_RESULT_PRESERVED",
    response["type"] == "TOOL_RESULT"
    and response["result"]["ok"] is True,
)

print("[TEST] ALL PASS: Audit Event ID Failure")
