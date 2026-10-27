
import json
import logging
import threading

from concurrent.futures import ThreadPoolExecutor

from webhook_notification_recovery_agent_observability import (
    WebhookNotificationRecoveryAgentObservability,
)
from webhook_notification_recovery_llm_safe_agent import (
    WebhookNotificationRecoveryLLMSafeAgent,
)
from webhook_notification_recovery_trace_context import (
    get_request_id,
)


TOOL_NAME = "get_webhook_recovery_health"


class FakeLLM:

    def __init__(self, barrier=None):
        self.barrier = barrier
        self.seen = {}
        self.lock = threading.Lock()

    def decide(self, message):
        request_id = get_request_id()

        with self.lock:
            self.seen[message] = request_id

        if self.barrier:
            self.barrier.wait(timeout=5)

        return {
            "decision": "TOOL_CALL",
            "name": TOOL_NAME,
            "arguments": "{}",
        }


class FakeScheduler:

    def __init__(self, failing_message=None):
        self.failing_message = failing_message
        self.seen = {}
        self.recovery_calls = 0
        self.lock = threading.Lock()

    def get_health_snapshot(self):
        request_id = get_request_id()

        with self.lock:
            self.seen[request_id] = (
                threading.get_ident()
            )

        if request_id == self.failing_message:
            raise RuntimeError("internal-secret")

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
        with self.lock:
            self.recovery_calls += 1

        raise AssertionError(
            "Recovery must not execute"
        )


class MemoryHandler(logging.Handler):

    def __init__(self):
        super().__init__()
        self.records = []
        self.lock_for_records = threading.Lock()

    def emit(self, record):
        with self.lock_for_records:
            self.records.append(
                record.getMessage()
            )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


def make_agent(llm, scheduler, handler):
    logger = logging.getLogger(
        "test.trace.concurrency"
    )
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(handler)

    safe_agent = (
        WebhookNotificationRecoveryLLMSafeAgent(
            scheduler=scheduler,
            llm=llm,
        )
    )

    return (
        WebhookNotificationRecoveryAgentObservability(
            agent=safe_agent,
            logger=logger,
        )
    )


# =====================================
# Scenario 1: Concurrent requests
# =====================================

request_count = 8

barrier = threading.Barrier(request_count)
llm = FakeLLM(barrier=barrier)
scheduler = FakeScheduler()
handler = MemoryHandler()

agent = make_agent(llm, scheduler, handler)


def execute_request(index):
    message = f"request-{index}"

    before = get_request_id()
    result = agent.run(message)
    after = get_request_id()

    return {
        "message": message,
        "before": before,
        "after": after,
        "result": result,
    }


with ThreadPoolExecutor(
    max_workers=request_count
) as executor:
    results = list(
        executor.map(
            execute_request,
            range(request_count),
        )
    )


check(
    "CONCURRENT_REQUEST_COUNT",
    len(results) == request_count,
)

check(
    "ALL_REQUESTS_SUCCESS",
    all(
        item["result"]["ok"] is True
        for item in results
    ),
)

ids = [
    item["result"]["request_id"]
    for item in results
]

check(
    "CONCURRENT_IDS_UNIQUE",
    len(set(ids)) == request_count,
)

check(
    "LLM_CONTEXT_MATCH",
    all(
        llm.seen[item["message"]]
        == item["result"]["request_id"]
        for item in results
    ),
)

check(
    "SCHEDULER_CONTEXT_MATCH",
    all(
        item["result"]["request_id"]
        in scheduler.seen
        for item in results
    ),
)

check(
    "CONTEXT_CLEANED",
    all(
        item["before"] is None
        and item["after"] is None
        for item in results
    ),
)

check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)

events = [
    json.loads(record)
    for record in handler.records
]

check(
    "CONCURRENT_LOG_COUNT",
    len(events) == request_count,
)

check(
    "LOG_IDS_MATCH",
    {
        event["request_id"]
        for event in events
    } == set(ids),
)


# =====================================
# Scenario 2: Failure isolation
# =====================================

class FailingLLM:

    def decide(self, message):
        if message == "fail":
            raise RuntimeError("llm-secret")

        return {
            "decision": "DIRECT_ANSWER",
            "answer": "OK",
        }


failure_handler = MemoryHandler()
failure_agent = make_agent(
    FailingLLM(),
    FakeScheduler(),
    failure_handler,
)


def execute_failure_case(message):
    before = get_request_id()
    result = failure_agent.run(message)
    after = get_request_id()

    return message, before, result, after


with ThreadPoolExecutor(
    max_workers=3
) as executor:
    failure_results = list(
        executor.map(
            execute_failure_case,
            ["ok-1", "fail", "ok-2"],
        )
    )


by_message = {
    message: (before, result, after)
    for message, before, result, after
    in failure_results
}

check(
    "FAILED_REQUEST_ISOLATED",
    by_message["fail"][1]["ok"] is False
    and by_message["ok-1"][1]["ok"] is True
    and by_message["ok-2"][1]["ok"] is True,
)

check(
    "FAILURE_CONTEXT_CLEANED",
    all(
        before is None and after is None
        for before, _, after
        in by_message.values()
    ),
)

check(
    "FAILURE_SECRET_NOT_LOGGED",
    all(
        "llm-secret" not in record
        for record in failure_handler.records
    ),
)


# =====================================
# Scenario 3: Thread reuse
# =====================================

reuse_handler = MemoryHandler()
reuse_agent = make_agent(
    FailingLLM(),
    FakeScheduler(),
    reuse_handler,
)


def execute_reused_thread(message):
    thread_id = threading.get_ident()
    before = get_request_id()
    result = reuse_agent.run(message)
    after = get_request_id()

    return thread_id, before, result, after


with ThreadPoolExecutor(
    max_workers=1
) as executor:
    reused = list(
        executor.map(
            execute_reused_thread,
            ["first", "second", "third"],
        )
    )


check(
    "SAME_THREAD_REUSED",
    len({
        item[0]
        for item in reused
    }) == 1,
)

check(
    "REUSED_THREAD_CONTEXT_CLEAN",
    all(
        before is None and after is None
        for _, before, _, after in reused
    ),
)

check(
    "REUSED_THREAD_IDS_UNIQUE",
    len({
        result["request_id"]
        for _, _, result, _ in reused
    }) == 3,
)


# =====================================
# Scenario 4: JSON compatibility
# =====================================

for item in results:
    json.dumps(item["result"])

check(
    "CONCURRENT_RESULTS_JSON_COMPATIBLE",
    True,
)


print(
    "[TEST] ALL PASS: "
    "Recovery Agent trace concurrency"
)
