"""On-demand analysis of a JOB query result, without database access."""
import json
from urllib.parse import urlparse

from job_abnormal_summary import build_abnormal_summary


def analyze_job_abnormalities(result, *, client, model):
    summary = build_abnormal_summary(result)
    evidence = [
        {
            "row": index,
            "status": job.get("status"),
            **({"duration_seconds": job["duration_seconds"]}
               if type(job.get("duration_seconds")) is int and job["duration_seconds"] >= 0
               else {}),
        }
        for index, job in enumerate(result["jobs"][:20], start=1)
        if isinstance(job, dict) and job.get("status") in ("FAILED", "TIMEOUT")
    ]
    report = {"facts": {"summary": summary, "rows": evidence}}
    if not evidence:
        return {**report, "status": "no_evidence"}

    try:
        options = {}
        if urlparse(str(getattr(client, 'base_url', ''))).hostname == 'api.deepseek.com':
            options = {'reasoning': {'effort': 'none'},
                       'text': {'format': {'type': 'json_object'}}}
        response = client.with_options(timeout=10, max_retries=0).responses.create(
            model=model,
            instructions=(
                "用中文分析 JOB 异常。状态不足以确认根因，明确表达不确定性。"
                "只输出 JSON 对象，包含 possible_causes 和 next_steps 两个非空字符串数组。"
                "给出可执行的只读排查建议，不声称已执行操作。"
            ),
            input=json.dumps(evidence),
            max_output_tokens=500,
            store=False,
            **options,
        )
        analysis = json.loads(response.output_text)
        fields = ("possible_causes", "next_steps")
        if not isinstance(analysis, dict) or any(
            not isinstance(analysis.get(field), list)
            or not 1 <= len(analysis[field]) <= 5
            or any(not isinstance(item, str) or not item.strip() or len(item) > 500
                   for item in analysis[field])
            for field in fields
        ):
            raise ValueError("invalid analysis")
    except Exception:
        return {**report, "status": "unavailable"}

    return {**report, "status": "ok", **{field: analysis[field] for field in fields}}
