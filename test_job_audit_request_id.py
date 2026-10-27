
from job_monitoring_audit import build_job_monitoring_audit
from webhook_notification_recovery_trace_context import get_request_id, reset_request_id, set_request_id


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


tool_result = {
    "schema_version": "1.1",
    "tool_name": "get_recent_abnormal_jobs",
    "abnormal_count": 0,
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "jobs": [],
}

original_id = get_request_id()

token = set_request_id("REQ-BN3-001")

try:
    audit = build_job_monitoring_audit(tool_result)

    check(
        "REQUEST_ID_INCLUDED",
        audit.get("request_id") == "REQ-BN3-001",
    )

    check(
        "AUDIT_EVENT_UNCHANGED",
        audit["event"] == "JOB_MONITORING_SUMMARY",
    )

    check(
        "COUNTS_UNCHANGED",
        audit["total_abnormal_count"] == 0
        and audit["returned_count"] == 0,
    )

    check(
        "TOOL_RESULT_NOT_MODIFIED",
        "request_id" not in tool_result,
    )

finally:
    reset_request_id(token)


check(
    "CONTEXT_RESTORED",
    get_request_id() == original_id,
)

print("[TEST] ALL PASS: Job Audit Request ID")
