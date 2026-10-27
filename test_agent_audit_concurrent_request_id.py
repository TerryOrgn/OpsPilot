
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from opspilot_multi_tool_safe_agent import OpsPilotMultiToolSafeAgent
from job_audit_recorder import JobAuditRecorder
from webhook_notification_recovery_trace_context import get_request_id, set_request_id, reset_request_id


# 请复制 BN-3E 中已验证成功的实际导入语句：
# from 实际模块名 import (
#     get_request_id, set_request_id, reset_request_id
# )


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


class ThreadSafeSink:
    def __init__(self):
        self.records = []
        self.lock = threading.Lock()

    def write(self, payload):
        with self.lock:
            self.records.append(payload)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


sink = ThreadSafeSink()

agent = OpsPilotMultiToolSafeAgent(
    scheduler=FakeScheduler(),
    job_repository=FakeRepository(),
    llm=FakeLLM(),
    audit_recorder=JobAuditRecorder(sink),
)

barrier = threading.Barrier(2)
main_context_before = get_request_id()


def run_request(request_id):
    before = get_request_id()
    token = set_request_id(request_id)

    try:
        # 确保两个线程均已设置各自的 Request ID
        barrier.wait(timeout=10)

        response = agent.ask("检查异常JOB")

        during = get_request_id()

        return {
            "request_id": request_id,
            "response": response,
            "before": before,
            "during": during,
        }
    finally:
        reset_request_id(token)


with ThreadPoolExecutor(max_workers=2) as executor:
    future_a = executor.submit(run_request, "REQ-BN4-A")
    future_b = executor.submit(run_request, "REQ-BN4-B")

    result_a = future_a.result(timeout=20)
    result_b = future_b.result(timeout=20)


results = [result_a, result_b]

check(
    "BOTH_REQUESTS_SUCCESS",
    all(r["response"]["ok"] is True for r in results),
)

check(
    "REQUEST_A_ID",
    result_a["response"]["audit"]["request_id"]
    == "REQ-BN4-A",
)

check(
    "REQUEST_B_ID",
    result_b["response"]["audit"]["request_id"]
    == "REQ-BN4-B",
)

check(
    "RECORDING_SUCCESS",
    all(
        r["response"].get("audit_recording_status") == "SUCCESS"
        for r in results
    ),
)

check(
    "TWO_SINK_RECORDS",
    len(sink.records) == 2,
)

saved = [json.loads(payload) for payload in sink.records]

saved_ids = {item["request_id"] for item in saved}

check(
    "SINK_IDS_ISOLATED",
    saved_ids == {"REQ-BN4-A", "REQ-BN4-B"},
)

check(
    "THREAD_CONTEXT_CORRECT",
    all(r["during"] == r["request_id"] for r in results),
)

check(
    "THREAD_CONTEXT_INITIAL_EMPTY",
    all(r["before"] is None for r in results),
)

check(
    "MAIN_CONTEXT_UNCHANGED",
    get_request_id() == main_context_before,
)

print("[TEST] ALL PASS: Concurrent Audit Request ID")
