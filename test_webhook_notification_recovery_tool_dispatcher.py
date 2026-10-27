
import json
from datetime import datetime

from webhook_notification_recovery_tool_dispatcher import (
    WebhookNotificationRecoveryToolDispatcher,
)


class FakeScheduler:

    def __init__(self):
        self.snapshot_calls = 0
        self.run_calls = 0
        self.fail = False

    def get_health_snapshot(self):
        self.snapshot_calls += 1

        if self.fail:
            raise RuntimeError(
                "Simulated internal database error"
            )

        return {
            "scheduler_health": "HEALTHY",
            "health_reason": "RUNNING_NORMALLY",
            "recovery_status": "EXECUTED",
            "ready_for_recovery": True,
            "readiness_reason": "READY",
            "total_runs": 5,
            "consecutive_failures": 0,
            "last_success_time": datetime(
                2026, 10, 23, 14, 30, 0
            ),
        }

    def run_once(self):
        self.run_calls += 1
        raise AssertionError(
            "Recovery must never be executed"
        )


scheduler = FakeScheduler()

dispatcher = WebhookNotificationRecoveryToolDispatcher(
    scheduler=scheduler
)

TOOL_NAME = "get_webhook_recovery_health"


# 1. Valid tool call
response = dispatcher.dispatch(
    TOOL_NAME,
    "{}",
)

assert response["ok"] is True
assert response["tool_name"] == TOOL_NAME
assert response["result"]["schema_version"] == "1.0"

print("[TEST] VALID_TOOL_CALL= True")


# 2. JSON-compatible response
encoded = json.dumps(response)
decoded = json.loads(encoded)

assert decoded == response

print("[TEST] RESPONSE_JSON_COMPATIBLE= True")


# 3. Unknown tool rejected
before = scheduler.snapshot_calls

response = dispatcher.dispatch(
    "delete_all_notifications",
    "{}",
)

assert response["ok"] is False
assert response["error"]["code"] == "UNKNOWN_TOOL"
assert scheduler.snapshot_calls == before

print("[TEST] UNKNOWN_TOOL_REJECTED= True")


# 4. Extra arguments rejected
before = scheduler.snapshot_calls

response = dispatcher.dispatch(
    TOOL_NAME,
    '{"force": true}',
)

assert response["error"]["code"] == (
    "UNEXPECTED_ARGUMENTS"
)
assert scheduler.snapshot_calls == before

print("[TEST] EXTRA_ARGUMENTS_REJECTED= True")


# 5. Invalid JSON rejected
response = dispatcher.dispatch(
    TOOL_NAME,
    "{invalid-json}",
)

assert response["error"]["code"] == "INVALID_JSON"

print("[TEST] INVALID_JSON_REJECTED= True")


# 6. JSON array rejected
response = dispatcher.dispatch(
    TOOL_NAME,
    "[]",
)

assert response["error"]["code"] == (
    "INVALID_ARGUMENTS"
)

print("[TEST] ARRAY_ARGUMENTS_REJECTED= True")


# 7. Null arguments rejected
response = dispatcher.dispatch(
    TOOL_NAME,
    "null",
)

assert response["error"]["code"] == (
    "INVALID_ARGUMENTS"
)

print("[TEST] NULL_ARGUMENTS_REJECTED= True")


# 8. Non-string arguments rejected
response = dispatcher.dispatch(
    TOOL_NAME,
    {},
)

assert response["error"]["code"] == (
    "INVALID_ARGUMENTS"
)

print("[TEST] NON_STRING_ARGUMENTS_REJECTED= True")


# 9. Internal execution failure handled
scheduler.fail = True

response = dispatcher.dispatch(
    TOOL_NAME,
    "{}",
)

assert response["ok"] is False
assert response["error"]["code"] == (
    "TOOL_EXECUTION_FAILED"
)

print("[TEST] EXECUTION_FAILURE_HANDLED= True")


# 10. Internal error details not exposed
encoded = json.dumps(response)

assert "database error" not in encoded.lower()
assert "RuntimeError" not in encoded

print("[TEST] INTERNAL_ERROR_HIDDEN= True")


# 11. Recovery never executed
assert scheduler.run_calls == 0

print("[TEST] RECOVERY_NEVER_EXECUTED= True")


# 12. Tool works after recovery
scheduler.fail = False

response = dispatcher.dispatch(
    TOOL_NAME,
    "{}",
)

assert response["ok"] is True
assert response["result"]["scheduler_health"] == (
    "HEALTHY"
)

print("[TEST] TOOL_RECOVERED= True")


# 13. Missing scheduler rejected
try:
    WebhookNotificationRecoveryToolDispatcher(
        scheduler=None
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "Missing scheduler must be rejected"
    )

print("[TEST] MISSING_SCHEDULER_REJECTED= True")


# 14. Final safety check
assert scheduler.run_calls == 0
assert scheduler.snapshot_calls == 3

print("[TEST] FINAL_SAFETY_CHECK= True")


print(
    "[TEST] ALL PASS: "
    "Recovery Agent tool dispatcher"
)
