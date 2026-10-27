
import json

from job_monitoring_audit import (
    build_job_monitoring_audit,
)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


tool_result = {
    "schema_version": "1.1",
    "tool_name": "get_recent_abnormal_jobs",
    "abnormal_count": 2,
    "total_abnormal_count": 3,
    "returned_count": 2,
    "truncated": True,
    "jobs": [
        {
            "execution_id": "EXEC-001",
            "job_name": "MonthEndJob",
            "status": "FAILED",
        },
        {
            "execution_id": "EXEC-002",
            "job_name": "ReportJob",
            "status": "TIMEOUT",
        },
    ],
}

audit = build_job_monitoring_audit(tool_result)

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
    audit["total_abnormal_count"] == 3,
)

check(
    "RETURNED_COUNT",
    audit["returned_count"] == 2,
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
    "EXPECTED_FIELDS",
    set(audit) == {
        "event",
        "tool_name",
        "total_abnormal_count",
        "returned_count",
        "truncated",
        "summary_status",
    },
)

invalid_result = {
    **tool_result,
    "total_abnormal_count": 1,
}

try:
    build_job_monitoring_audit(invalid_result)
except ValueError:
    invalid_rejected = True
else:
    invalid_rejected = False

check(
    "INVALID_METADATA_REJECTED",
    invalid_rejected,
)

print(
    "[TEST] AUDIT=",
    json.dumps(audit, ensure_ascii=False),
)

print("[TEST] ALL PASS: Job Monitoring Audit")
