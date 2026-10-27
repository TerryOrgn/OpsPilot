
import json

from webhook_notification_recovery_health_tool import (
    WebhookNotificationRecoveryHealthTool,
)
from webhook_notification_recovery_tool_definition import (
    WebhookNotificationRecoveryToolDefinition,
)


def get_definition():
    return (
        WebhookNotificationRecoveryToolDefinition
        .get_definition()
    )


# 1. 定义类型
definition = get_definition()

assert definition["type"] == "function"
print("[TEST] FUNCTION_TYPE_VALID= True")


# 2. 工具名称与 Adapter 一致
function = definition["function"]

assert function["name"] == (
    WebhookNotificationRecoveryHealthTool.TOOL_NAME
)
print("[TEST] TOOL_NAME_MATCHES_ADAPTER= True")


# 3. 描述与 Adapter 一致
assert function["description"] == (
    WebhookNotificationRecoveryHealthTool
    .TOOL_DESCRIPTION
)
print("[TEST] DESCRIPTION_MATCHES_ADAPTER= True")


# 4. 参数类型为 object
parameters = function["parameters"]

assert parameters["type"] == "object"
print("[TEST] PARAMETERS_OBJECT= True")


# 5. 不接受任何业务参数
assert parameters["properties"] == {}
assert parameters["required"] == []

print("[TEST] NO_ARGUMENTS_REQUIRED= True")


# 6. 禁止额外参数
assert parameters["additionalProperties"] is False

print("[TEST] EXTRA_ARGUMENTS_FORBIDDEN= True")


# 7. JSON 可序列化
encoded = json.dumps(definition)
decoded = json.loads(encoded)

assert decoded == definition
print("[TEST] DEFINITION_JSON_COMPATIBLE= True")


# 8. 定义字段结构正确
assert set(definition.keys()) == {
    "type",
    "function",
}

assert set(function.keys()) == {
    "name",
    "description",
    "parameters",
}

print("[TEST] DEFINITION_SCHEMA_VALID= True")


# 9. 每次返回独立对象
first = get_definition()
second = get_definition()

assert first is not second
assert first == second

print("[TEST] INDEPENDENT_DEFINITION= True")


# 10. 修改返回值不影响下一次调用
first["function"]["name"] = "modified"
first["function"]["parameters"][
    "additionalProperties"
] = True

fresh = get_definition()

assert fresh["function"]["name"] == (
    WebhookNotificationRecoveryHealthTool.TOOL_NAME
)

assert fresh["function"]["parameters"][
    "additionalProperties"
] is False

print("[TEST] DEFINITION_MUTATION_ISOLATED= True")


# 11. 不依赖 Scheduler 实例
definition = get_definition()

assert definition["function"]["name"]
assert "scheduler" not in definition

print("[TEST] NO_SCHEDULER_DEPENDENCY= True")


# 12. 输出最终定义
print(
    "[INFO] TOOL_DEFINITION=",
    json.dumps(
        definition,
        ensure_ascii=False,
        indent=2,
    ),
)

assert definition["function"]["parameters"][
    "properties"
] == {}

print("[TEST] FINAL_DEFINITION_VALID= True")


print(
    "[TEST] ALL PASS: "
    "Recovery Agent tool definition"
)
