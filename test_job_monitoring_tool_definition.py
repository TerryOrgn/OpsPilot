
import json

from job_monitoring_tool import JobMonitoringTool
from job_monitoring_tool_definition import (
    JobMonitoringToolDefinition,
)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}= True")


definition = (
    JobMonitoringToolDefinition.get_definition()
)

parameters = definition["parameters"]
properties = parameters["properties"]
limit_schema = properties["limit"]


check(
    "FUNCTION_TYPE",
    definition["type"] == "function",
)

check(
    "TOOL_NAME_MATCH",
    definition["name"]
    == JobMonitoringTool.TOOL_NAME,
)

check(
    "STRICT_MODE_ENABLED",
    definition["strict"] is True,
)

check(
    "PARAMETERS_OBJECT",
    parameters["type"] == "object",
)

check(
    "LIMIT_DEFINED",
    "limit" in properties,
)

check(
    "LIMIT_INTEGER",
    limit_schema["type"] == "integer",
)

check(
    "LIMIT_REQUIRED",
    parameters["required"] == ["limit"],
)

check(
    "ADDITIONAL_PROPERTIES_REJECTED",
    parameters["additionalProperties"] is False,
)

check(
    "ONLY_LIMIT_PARAMETER",
    set(properties.keys()) == {"limit"},
)

check(
    "READ_ONLY_DESCRIPTION",
    "read-only" in definition["description"],
)

check(
    "NO_UNSUPPORTED_RANGE_KEYWORDS",
    "minimum" not in limit_schema
    and "maximum" not in limit_schema,
)

check(
    "LIMIT_RANGE_DOCUMENTED",
    "1 and 100" in limit_schema["description"],
)

check(
    "TOOL_NAME_JSON_COMPATIBLE",
    isinstance(definition["name"], str),
)

json.dumps(definition)

check(
    "DEFINITION_JSON_COMPATIBLE",
    True,
)

first = JobMonitoringToolDefinition.get_definition()
second = JobMonitoringToolDefinition.get_definition()

check(
    "INDEPENDENT_DEFINITION_OBJECTS",
    first is not second
    and first["parameters"]
    is not second["parameters"],
)


print(
    "[TEST] ALL PASS: "
    "Job Monitoring Tool Definition"
)
