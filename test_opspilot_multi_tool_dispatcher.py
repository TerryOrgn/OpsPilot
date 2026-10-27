
import json

from opspilot_multi_tool_dispatcher import (
    OpsPilotMultiToolDispatcher,
)


HEALTH_TOOL = "get_webhook_recovery_health"
JOB_TOOL = "get_recent_abnormal_jobs"


class FakeScheduler:

    def __init__(self):
        self.health_calls = 0
        self.recovery_calls = 0
        self.fail_health = False

    def get_health_snapshot(self):
        self.health_calls += 1

        if self.fail_health:
            raise RuntimeError("scheduler-secret")

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


class FakeJobRepository:

    def __init__(self):
        self.calls = 0
        self.fail = False

    def get_recent_jobs(self):
        self.calls += 1

        if self.fail:
            raise RuntimeError("database-secret")

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


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


scheduler = FakeScheduler()
repository = FakeJobRepository()

dispatcher = OpsPilotMultiToolDispatcher(
    scheduler=scheduler,
    job_repository=repository,
)


# 1. Health tool
health = dispatcher.dispatch(
    HEALTH_TOOL, "{}"
)

check(
    "HEALTH_TOOL_SUCCESS",
    health["ok"] is True,
)

check(
    "HEALTH_TOOL_NAME",
    health["tool_name"] == HEALTH_TOOL,
)


# 2. JOB tool
jobs = dispatcher.dispatch(
    JOB_TOOL, '{"limit": 10}'
)

check(
    "JOB_TOOL_SUCCESS",
    jobs["ok"] is True,
)

check(
    "JOB_ABNORMAL_COUNT",
    jobs["result"]["abnormal_count"] == 2,
)

check(
    "JOB_ONLY_ABNORMAL",
    {
        job["status"]
        for job in jobs["result"]["jobs"]
    } == {"FAILED", "TIMEOUT"},
)


# 3. Limit
limited = dispatcher.dispatch(
    JOB_TOOL, '{"limit": 1}'
)

check(
    "JOB_LIMIT_APPLIED",
    limited["result"]["abnormal_count"] == 1,
)


# 4. Unknown tool
unknown = dispatcher.dispatch(
    "delete_all_jobs", "{}"
)

check(
    "UNKNOWN_TOOL_REJECTED",
    unknown["error"]["code"] == "UNKNOWN_TOOL",
)


# 5. Invalid arguments
invalid = dispatcher.dispatch(
    JOB_TOOL, '{"limit": 0}'
)

check(
    "INVALID_LIMIT_REJECTED",
    invalid["error"]["code"]
    == "INVALID_ARGUMENTS",
)

extra = dispatcher.dispatch(
    JOB_TOOL,
    '{"limit": 5, "delete": true}'
)

check(
    "EXTRA_ARGUMENTS_REJECTED",
    extra["error"]["code"]
    == "INVALID_ARGUMENTS",
)

missing = dispatcher.dispatch(
    JOB_TOOL, "{}"
)

check(
    "MISSING_LIMIT_REJECTED",
    missing["error"]["code"]
    == "INVALID_ARGUMENTS",
)

boolean = dispatcher.dispatch(
    JOB_TOOL, '{"limit": true}'
)

check(
    "BOOLEAN_LIMIT_REJECTED",
    boolean["error"]["code"]
    == "INVALID_ARGUMENTS",
)


# 6. Health isolation
health_extra = dispatcher.dispatch(
    HEALTH_TOOL, '{"limit": 5}'
)

check(
    "HEALTH_EXTRA_ARGUMENTS_REJECTED",
    health_extra["error"]["code"]
    == "UNEXPECTED_ARGUMENTS",
)


# 7. Malformed JSON
malformed = dispatcher.dispatch(
    JOB_TOOL, "{invalid"
)

check(
    "MALFORMED_JSON_REJECTED",
    malformed["error"]["code"] == "INVALID_JSON",
)


# 8. Tool exception isolation
repository.fail = True

failed_jobs = dispatcher.dispatch(
    JOB_TOOL, '{"limit": 10}'
)

check(
    "JOB_EXCEPTION_ISOLATED",
    failed_jobs["error"]["code"]
    == "TOOL_EXECUTION_FAILED",
)

check(
    "DATABASE_SECRET_HIDDEN",
    "database-secret"
    not in json.dumps(failed_jobs),
)

repository.fail = False


# 9. Scheduler exception isolation
scheduler.fail_health = True

failed_health = dispatcher.dispatch(
    HEALTH_TOOL, "{}"
)

check(
    "HEALTH_EXCEPTION_ISOLATED",
    failed_health["error"]["code"]
    == "TOOL_EXECUTION_FAILED",
)

scheduler.fail_health = False


# 10. No recovery execution
check(
    "RECOVERY_NEVER_EXECUTED",
    scheduler.recovery_calls == 0,
)


# 11. JSON compatibility
json.dumps(health)
json.dumps(jobs)
json.dumps(failed_jobs)

check(
    "RESULTS_JSON_COMPATIBLE",
    True,
)


# 12. Dependency validation
try:
    OpsPilotMultiToolDispatcher(
        scheduler=None,
        job_repository=repository,
    )
except ValueError:
    rejected = True
else:
    rejected = False

check(
    "MISSING_SCHEDULER_REJECTED",
    rejected,
)

try:
    OpsPilotMultiToolDispatcher(
        scheduler=scheduler,
        job_repository=None,
    )
except ValueError:
    rejected = True
else:
    rejected = False

check(
    "MISSING_REPOSITORY_REJECTED",
    rejected,
)


print(
    "[TEST] ALL PASS: "
    "OpsPilot Multi Tool Dispatcher"
)
