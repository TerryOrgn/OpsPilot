
from webhook_notification_recovery_tool_dispatcher import (
    WebhookNotificationRecoveryToolDispatcher,
)



class FakeLLM:
    """
    Rule-based simulator for tool calling decisions.

    No external model or API calls.
    """

    TOOL_NAME = "get_webhook_recovery_health"

    HEALTH_KEYWORDS = (
        "健康",
        "状态",
        "正常",
        "health",
        "status",
    )

    RECOVERY_KEYWORDS = (
        "recovery",
        "webhook",
        "恢复调度器",
        "恢复任务",
    )

    BLOCKED_KEYWORDS = (
        "删除",
        "清空",
        "delete",
        "drop",
        "truncate",
    )

    def __init__(self):
        self.tool_requests = 0
        self.answer_requests = 0

    def select_tool(self, user_message):
        self.tool_requests += 1

        message = user_message.lower()

        # 1. Reject potentially destructive requests.
        if any(
            keyword in message
            for keyword in self.BLOCKED_KEYWORDS
        ):
            return {
                "decision": "DIRECT_ANSWER",
                "answer": (
                    "当前 Agent 仅支持只读健康查询，"
                    "不允许执行删除或清空操作。"
                ),
            }

        # 2. Match the recovery health query intent.
        has_health_intent = any(
            keyword in message
            for keyword in self.HEALTH_KEYWORDS
        )

        has_recovery_context = any(
            keyword in message
            for keyword in self.RECOVERY_KEYWORDS
        )

        if has_health_intent and has_recovery_context:
            return {
                "decision": "TOOL_CALL",
                "name": self.TOOL_NAME,
                "arguments": "{}",
            }

        # 3. Default to no tool call.
        return {
            "decision": "DIRECT_ANSWER",
            "answer": (
                "我目前只支持查询 Webhook Recovery "
                "调度器的健康状态。"
            ),
        }

    def generate_answer(self, tool_response):
        self.answer_requests += 1

        if not tool_response["ok"]:
            error_code = tool_response["error"]["code"]
            return (
                "无法获取 Webhook Recovery 健康状态。"
                f"错误代码：{error_code}。"
            )

        data = tool_response["result"]

        health = data["scheduler_health"]
        recovery = data["recovery_status"]
        ready = data["ready_for_recovery"]

        if health == "HEALTHY":
            health_text = "健康"
        elif health == "DEGRADED":
            health_text = "降级"
        else:
            health_text = "不健康"

        readiness_text = (
            "当前允许执行 Recovery"
            if ready
            else "当前不满足 Recovery 就绪条件"
        )

        return (
            f"Webhook Recovery 调度器当前{health_text}。"
            f"最近一次 Recovery 状态：{recovery}。"
            f"{readiness_text}。"
        )



class WebhookNotificationRecoveryAgentLoop:

    def __init__(self, scheduler, llm=None):
        self._llm = llm or FakeLLM()

        self._dispatcher = (
            WebhookNotificationRecoveryToolDispatcher(
                scheduler=scheduler
            )
        )


    def run(self, user_message):
        if (
                not isinstance(user_message, str)
                or not user_message.strip()
        ):
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_USER_MESSAGE",
                    "message": "User message must be non-empty",
                },
            }

        # Step 1: Simulated LLM decides what to do.
        decision = self._llm.select_tool(user_message)

        # Step 2: Direct answer, no tool execution.
        if decision["decision"] == "DIRECT_ANSWER":
            return {
                "ok": True,
                "decision": "DIRECT_ANSWER",
                "tool_name": None,
                "tool_response": None,
                "answer": decision["answer"],
            }

        # Step 3: Reject unsupported decision types.
        if decision["decision"] != "TOOL_CALL":
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_DECISION",
                    "message": "Unsupported tool decision",
                },
            }

        # Step 4: Dispatcher validates and executes.
        tool_response = self._dispatcher.dispatch(
            decision["name"],
            decision["arguments"],
        )

        # Step 5: Generate the final answer.
        answer = self._llm.generate_answer(
            tool_response
        )

        return {
            "ok": tool_response["ok"],
            "decision": "TOOL_CALL",
            "tool_name": decision["name"],
            "tool_response": tool_response,
            "answer": answer,
        }

        if (
            not isinstance(user_message, str)
            or not user_message.strip()
        ):
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_USER_MESSAGE",
                    "message": "User message must be non-empty",
                },
            }

        # Step 1: Simulated LLM selects a tool
        tool_call = self._llm.select_tool(user_message)

        # Step 2: Dispatcher validates and executes
        tool_response = self._dispatcher.dispatch(
            tool_call["name"],
            tool_call["arguments"],
        )

        # Step 3: Simulated LLM generates final answer
        answer = self._llm.generate_answer(
            tool_response
        )

        return {
            "ok": tool_response["ok"],
            "tool_name": tool_call["name"],
            "tool_response": tool_response,
            "answer": answer,
        }
