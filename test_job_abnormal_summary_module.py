
from job_abnormal_summary import build_abnormal_summary


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def rejected(result):
    try:
        build_abnormal_summary(result)
    except ValueError:
        return True
    return False


base = {
    "schema_version": "1.1",
    "tool_name": "get_recent_abnormal_jobs",
    "abnormal_count": 2,
    "total_abnormal_count": 3,
    "returned_count": 2,
    "truncated": True,
    "jobs": [
        {"execution_id": "EXEC-001", "status": "FAILED"},
        {"execution_id": "EXEC-002", "status": "TIMEOUT"},
    ],
}

summary = build_abnormal_summary(base)

check(
    "TOTAL_COUNT",
    "共识别出3条异常" in summary,
)

check(
    "RETURNED_COUNT",
    "展示2条异常明细" in summary,
)

check(
    "MISSING_COUNT",
    "还有1条异常未展示明细" in summary,
)

check(
    "CANDIDATE_SCOPE",
    "本次候选记录中" in summary,
)

complete = {
    **base,
    "total_abnormal_count": 2,
    "truncated": False,
}

check(
    "COMPLETE_SUMMARY",
    "已展示全部2条异常明细"
    in build_abnormal_summary(complete),
)

empty = {
    **base,
    "abnormal_count": 0,
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "jobs": [],
}

check(
    "EMPTY_SUMMARY",
    "共识别出0条异常"
    in build_abnormal_summary(empty),
)

check(
    "INVALID_SCHEMA_REJECTED",
    rejected({**base, "schema_version": "1.0"}),
)

check(
    "INVALID_TOOL_REJECTED",
    rejected({**base, "tool_name": "unknown"}),
)

check(
    "INVALID_COUNT_REJECTED",
    rejected({**base, "total_abnormal_count": -1}),
)

check(
    "BOOLEAN_COUNT_REJECTED",
    rejected({**base, "returned_count": True}),
)

check(
    "JOBS_LENGTH_MISMATCH_REJECTED",
    rejected({**base, "returned_count": 1}),
)

check(
    "LEGACY_COUNT_MISMATCH_REJECTED",
    rejected({**base, "abnormal_count": 1}),
)

check(
    "TRUNCATED_MISMATCH_REJECTED",
    rejected({**base, "truncated": False}),
)

check(
    "INPUT_NOT_MUTATED",
    base["total_abnormal_count"] == 3
    and len(base["jobs"]) == 2,
)

print("[TEST] SUMMARY=", summary)
print("[TEST] ALL PASS: Job Abnormal Summary Module")
