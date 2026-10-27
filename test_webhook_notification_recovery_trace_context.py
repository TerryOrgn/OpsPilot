
import json
import logging

from webhook_notification_recovery_agent_observability import (
    WebhookNotificationRecoveryAgentObservability,
)
from webhook_notification_recovery_llm_safe_agent import (
    WebhookNotificationRecoveryLLMSafeAgent,
)
from webhook_notification_recovery_trace_context import (
    get_request_id,
    set_request_id,
    reset_request_id,
)


TOOL_NAME = "get_webhook_recovery_health"


class FakeScheduler:

    def __init__(self):
        self.seen_request_ids = []
        self.recovery_calls = 0

    def get_health_snapshot(self):
        self.seen_request_ids.append(
            get_request_id()
        )

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
            "Recovery must not execute"
        )


class FakeLLM:

    def __init__(self):
        self.seen_request_ids = []

    def decide(self, user_message):
        self.seen_request_ids.append(
            get_request_id()
        )

        return {
            "decision": "TOOL_CALL",
            "name": TOOL_NAME,
            "arguments": "{}",
        }


class MemoryHandler(logging.Handler):

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(
            record.getMessage()
        )


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


scheduler = FakeScheduler()
llm = FakeLLM()

safe_agent = WebhookNotificationRecoveryLLMSafeAgent(
    scheduler=scheduler,
    llm=llm,
)

handler = MemoryHandler()
logger = logging.getLogger("test.trace.context")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(handler)

ids = iter(["req-001", "req-002"])
times = iter([1.0, 1.010, 2.0, 2.020])

agent = WebhookNotificationRecoveryAgentObservability(
    agent=safe_agent,
    logger=logger,
    clock=lambda: next(times),
    request_id_factory=lambda: next(ids),
)


# 1. Context initially empty
check(
    "INITIAL_CONTEXT_EMPTY",
    get_request_id() is None,
)


# 2. First request
first = agent.run("检查 Recovery 健康")

check(
    "FIRST_REQUEST_ID",
    first["request_id"] == "req-001",
)

check(
    "FIRST_REQUEST_SUCCESS",
    first["ok"] is True,
)


# 3. LLM receives same request ID
check(
    "LLM_CONTEXT_PROPAGATED",
    llm.seen_request_ids[0] == "req-001",
)


# 4. Health Tool reaches Scheduler
check(
    "SCHEDULER_CONTEXT_PROPAGATED",
    scheduler.seen_request_ids[0] == "req-001",
)


# 5. Context cleaned after request
check(
    "CONTEXT_CLEANED_AFTER_FIRST",
    get_request_id() is None,
)


# 6. Second request
second = agent.run("再次检查 Recovery")

check(
    "SECOND_REQUEST_ID",
    second["request_id"] == "req-002",
)


# 7. No cross-request contamination
check(
    "NO_CONTEXT_CROSSOVER",
    llm.seen_request_ids[1] == "req-002"
    and scheduler.seen_request_ids[1] == "req-002",
)


# 8. Context cleaned after second
check(
    "CONTEXT_CLEANED_AFTER_SECOND",
    get_request_id() is None,
)


# 9. Logs carry request IDs
events = [
    json.loads(record)
    for record in handler.records
]

check(
    "LOG_REQUEST_IDS_MATCH",
    len(events) == 2
    and events[0]["request_id"] == "req-001"
    and events[1]["request_id"] == "req-002",
)


# 10. Recovery never executed
check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)


# 11. Nested context restoration
outer_token = set_request_id("outer-request")
inner_token = set_request_id("inner-request")

check(
    "NESTED_CONTEXT_ACTIVE",
    get_request_id() == "inner-request",
)

reset_request_id(inner_token)

check(
    "OUTER_CONTEXT_RESTORED",
    get_request_id() == "outer-request",
)

reset_request_id(outer_token)

check(
    "FINAL_CONTEXT_CLEAN",
    get_request_id() is None,
)


# 12. Invalid ID rejected
try:
    set_request_id("")
except ValueError:
    rejected = True
else:
    rejected = False

check(
    "EMPTY_REQUEST_ID_REJECTED",
    rejected,
)


print(
    "[TEST] ALL PASS: "
    "Recovery Agent trace context"
)
