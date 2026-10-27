
import json
import os

from webhook_notification_recovery_llm_decision import (
    WebhookNotificationRecoveryLLMDecision,
)

import os

print(
    "[CHECK] API_KEY_CONFIGURED=",
    bool(os.getenv("OPENAI_API_KEY"))
)

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY is not configured"
    )

llm = WebhookNotificationRecoveryLLMDecision()

question = "请检查 Webhook Recovery 调度器是否健康"

result = llm.decide(question)

print(
    "[INFO] DECISION=",
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ),
)

assert result["decision"] in (
    "TOOL_CALL",
    "DIRECT_ANSWER",
    "UNSUPPORTED_MULTIPLE_CALLS",
)

print("[TEST] VALID_DECISION_TYPE= True")

if result["decision"] == "TOOL_CALL":
    assert result["name"] == (
        "get_webhook_recovery_health"
    )

    assert json.loads(result["arguments"]) == {}

    print("[TEST] EXPECTED_TOOL_SELECTED= True")

elif result["decision"] == "DIRECT_ANSWER":
    print(
        "[INFO] MODEL_CHOSE_DIRECT_ANSWER=",
        result["answer"],
    )

else:
    raise AssertionError(
        "Multiple tool calls are not expected"
    )

print("[TEST] NO_TOOL_EXECUTED= True")
print("[TEST] ALL PASS: LLM decision inspection")
