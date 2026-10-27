
from job_monitoring_tool import JobMonitoringTool


class JobMonitoringToolDefinition:

    @staticmethod
    def get_definition():
        return {
            "type": "function",
            "name": JobMonitoringTool.TOOL_NAME,
            "description": (
                "Read recent failed or timed-out JOB "
                "executions. This tool is read-only. "
                "It cannot restart, modify, or delete "
                "JOB executions. The result contains "
                "at most the requested number of "
                "abnormal JOB records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": (
                            "Maximum number of abnormal JOB records "
                            "to return. Must be between 1 and 100."
                        ),
                    }
                },
                "required": ["limit"],
                "additionalProperties": False,
            },
            "strict": True,
        }
