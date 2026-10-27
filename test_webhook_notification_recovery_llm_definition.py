
import json

from webhook_notification_recovery_llm_decision import (
    WebhookNotificationRecoveryLLMDecision,
)


tools = (
    WebhookNotificationRecoveryLLMDecision
    .get_tools()
)

assert len(tools) == 1
print("[TEST] SINGLE_TOOL= True")

tool = tools[0]

assert tool["type"] == "function"
print("[TEST] FUNCTION_TYPE= True")

assert tool["name"] == "get_webhook_recovery_health"
print("[TEST] TOOL_NAME= True")

assert tool["parameters"]["type"] == "object"
print("[TEST] OBJECT_PARAMETERS= True")

assert tool["parameters"]["properties"] == {}
print("[TEST] NO_PARAMETERS= True")

assert tool["parameters"]["additionalProperties"] is False
print("[TEST] EXTRA_ARGUMENTS_FORBIDDEN= True")

assert tool["strict"] is True
print("[TEST] STRICT_SCHEMA= True")

json.dumps(tools)
print("[TEST] JSON_COMPATIBLE= True")

print("[TEST] ALL PASS: LLM tool definition")
