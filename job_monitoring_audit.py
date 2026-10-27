
from job_abnormal_summary import build_abnormal_summary
from webhook_notification_recovery_trace_context import get_request_id


# 请替换为你项目中实际的 Trace Context 模块名


def build_job_monitoring_audit(tool_result):
    """
    Build structured JOB monitoring audit event.
    Reuse existing request context when available.
    """

    # Validate the tool result before creating audit metadata.
    build_abnormal_summary(tool_result)

    audit = {
        "event": "JOB_MONITORING_SUMMARY",
        "tool_name": tool_result["tool_name"],
        "total_abnormal_count": tool_result[
            "total_abnormal_count"
        ],
        "returned_count": tool_result["returned_count"],
        "truncated": tool_result["truncated"],
        "summary_status": "SUCCESS",
    }

    request_id = get_request_id()

    if request_id is not None:
        audit["request_id"] = request_id

    return audit

