
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from opspilot_multi_tool_safe_agent import OpsPilotMultiToolSafeAgent
from job_audit_recorder import JobAuditRecorder
from webhook_notification_recovery_trace_context import get_request_id, reset_request_id, set_request_id

# 请复制 BN-4A 中已经验证通过的实际导入语句：
# from 实际模块名 import (
#     get_request_id, set_request_id, reset_request_id
# )

THREAD_COUNT = 10
REQUEST_COUNT = 100


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

main_context_before = get_request_id()

# 让前 10 个任务同时进入 Agent
barrier = threading.Barrier(THREAD_COUNT)


def run_request(index):
    request_id = f"REQ-BN4B-{index:03d}"
    context_before = get_request_id()
    token = set_request_id(request_id)

    try:
        if index < THREAD_COUNT:
            barrier.wait(timeout=10)

        response = agent.ask("检查异常JOB")

        context_during = get_request_id()

        return {
            "request_id": request_id,
            "response": response,
            "context_before": context_before,
            "context_during": context_during,
        }
    finally:
        reset_request_id(token)


results = []
errors = []

with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
    futures = [
        executor.submit(run_request, i)
        for i in range(REQUEST_COUNT)
    ]

    for future in as_completed(futures):
        try:
            results.append(future.result(timeout=20))
        except Exception as exc:
            errors.append(repr(exc))


print(f"[STRESS] THREAD_COUNT={THREAD_COUNT}")
print(f"[STRESS] REQUEST_COUNT={REQUEST_COUNT}")
print(f"[STRESS] COMPLETED={len(results)}")
print(f"[STRESS] ERRORS={len(errors)}")

if errors:
    print(f"[STRESS] ERROR_SAMPLES={errors[:5]}")


check(
    "NO_EXECUTION_ERRORS",
    len(errors) == 0,
)

check(
    "ALL_REQUESTS_COMPLETED",
    len(results) == REQUEST_COUNT,
)

check(
    "ALL_AGENT_CALLS_SUCCESS",
    all(
        r["response"]["ok"] is True
        for r in results
    ),
)

check(
    "ALL_AUDIT_IDS_CORRECT",
    all(
        r["response"]["audit"].get("request_id")
        == r["request_id"]
        for r in results
    ),
)

check(
    "ALL_RECORDINGS_SUCCESS",
    all(
        r["response"].get("audit_recording_status")
        == "SUCCESS"
        for r in results
    ),
)

check(
    "SINK_RECORD_COUNT",
    len(sink.records) == REQUEST_COUNT,
)

saved = [
    json.loads(payload)
    for payload in sink.records
]

expected_ids = {
    f"REQ-BN4B-{i:03d}"
    for i in range(REQUEST_COUNT)
}

saved_ids = [
    record["request_id"]
    for record in saved
]

check(
    "NO_DUPLICATE_REQUEST_IDS",
    len(set(saved_ids)) == REQUEST_COUNT,
)

check(
    "SINK_REQUEST_IDS_COMPLETE",
    set(saved_ids) == expected_ids,
)

check(
    "THREAD_CONTEXT_CORRECT",
    all(
        r["context_during"] == r["request_id"]
        for r in results
    ),
)

check(
    "THREAD_CONTEXT_RESTORED",
    all(
        r["context_before"] is None
        for r in results
    ),
)

check(
    "MAIN_CONTEXT_UNCHANGED",
    get_request_id() == main_context_before,
)

print("[TEST] ALL PASS: Concurrent Audit Stress")
