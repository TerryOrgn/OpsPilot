
def build_abnormal_summary(result):
    """
    Build a deterministic summary from JobMonitoringTool Schema 1.1.

    Counts are scoped to the candidates returned by Repository.
    This function does not query a database or invoke an LLM.
    """
    if not isinstance(result, dict):
        raise ValueError("result must be a dictionary")

    if result.get("schema_version") != "1.1":
        raise ValueError("unsupported schema_version")

    if result.get("tool_name") != "get_recent_abnormal_jobs":
        raise ValueError("unsupported tool_name")

    jobs = result.get("jobs")
    total = result.get("total_abnormal_count")
    returned = result.get("returned_count")
    truncated = result.get("truncated")
    legacy_count = result.get("abnormal_count")

    if not isinstance(jobs, list):
        raise ValueError("jobs must be a list")

    for name, value in (
        ("total_abnormal_count", total),
        ("returned_count", returned),
        ("abnormal_count", legacy_count),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(f"invalid {name}")

    if not isinstance(truncated, bool):
        raise ValueError("truncated must be a boolean")

    if returned != len(jobs):
        raise ValueError("returned_count does not match jobs")

    if legacy_count != returned:
        raise ValueError("abnormal_count does not match returned_count")

    if total < returned:
        raise ValueError(
            "total_abnormal_count cannot be smaller than returned_count"
        )

    if truncated != (total > returned):
        raise ValueError("inconsistent truncated flag")

    missing = total - returned

    if truncated:
        return (
            f"本次候选记录中共识别出{total}条异常，"
            f"当前展示{returned}条异常明细，"
            f"还有{missing}条异常未展示明细。"
        )

    return (
        f"本次候选记录中共识别出{total}条异常，"
        f"已展示全部{returned}条异常明细。"
    )
