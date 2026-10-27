
def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


# 模拟 JobMonitoringTool Schema 1.1 的输出
tool_result = {
    "schema_version": "1.1",
    "tool_name": "get_recent_abnormal_jobs",
    "abnormal_count": 10,
    "total_abnormal_count": 15,
    "returned_count": 10,
    "truncated": True,
    "jobs": [
        {
            "execution_id": f"EXEC-{i:03d}",
            "job_name": "MonthEndJob",
            "status": "TIMEOUT",
        }
        for i in range(10)
    ],
}


def build_abnormal_summary(result):
    """
    根据 Tool 返回的统计字段生成确定性摘要。

    注意：
    这是 Python 规则逻辑，不是真实 LLM 推理。
    """
    total = result["total_abnormal_count"]
    returned = result["returned_count"]
    truncated = result["truncated"]

    if returned != len(result["jobs"]):
        raise ValueError(
            "returned_count does not match jobs length"
        )

    if total < returned:
        raise ValueError(
            "total_abnormal_count cannot be smaller "
            "than returned_count"
        )

    if truncated != (total > returned):
        raise ValueError(
            "truncated flag is inconsistent"
        )

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


summary = build_abnormal_summary(tool_result)

check(
    "TOTAL_COUNT_PRESERVED",
    "15条异常" in summary,
)

check(
    "RETURNED_COUNT_PRESERVED",
    "展示10条异常明细" in summary,
)

check(
    "MISSING_COUNT_CORRECT",
    "还有5条异常未展示明细" in summary,
)

check(
    "CANDIDATE_SCOPE_EXPLICIT",
    "本次候选记录中" in summary,
)

check(
    "NOT_CONFUSED_WITH_RETURNED_COUNT",
    "共识别出10条异常" not in summary,
)


# 验证未截断场景
complete_result = {
    **tool_result,
    "abnormal_count": 3,
    "total_abnormal_count": 3,
    "returned_count": 3,
    "truncated": False,
    "jobs": tool_result["jobs"][:3],
}

complete_summary = build_abnormal_summary(
    complete_result
)

check(
    "COMPLETE_RESULT",
    "已展示全部3条异常明细" in complete_summary,
)


# 验证不一致的元数据会被拒绝
invalid_result = {
    **tool_result,
    "total_abnormal_count": 8,
}

try:
    build_abnormal_summary(invalid_result)
except ValueError:
    invalid_rejected = True
else:
    invalid_rejected = False

check(
    "INCONSISTENT_METADATA_REJECTED",
    invalid_rejected,
)


print("[TEST] SUMMARY=", summary)
print("[TEST] COMPLETE_SUMMARY=", complete_summary)
print("[TEST] ALL PASS: Abnormal Summary Semantics")
