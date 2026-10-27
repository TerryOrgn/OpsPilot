
import json

from opspilot_multi_tool_dispatcher import (
    OpsPilotMultiToolDispatcher,
)
from job_abnormal_summary import build_abnormal_summary
from job_monitoring_audit import build_job_monitoring_audit
import uuid

class OpsPilotMultiToolSafeAgent:

    def __init__(
            self,
            scheduler,
            job_repository,
            llm,
            enable_job_timeout_detection=False,
            now_provider=None,
            audit_recorder=None,
    ):
        if llm is None:
            raise ValueError("llm is required")

        if (
                audit_recorder is not None
                and not callable(
            getattr(audit_recorder, "record", None)
        )
        ):
            raise ValueError(
                "audit_recorder must provide record()"
            )

        self._llm = llm
        self._audit_recorder = audit_recorder

        self._dispatcher = OpsPilotMultiToolDispatcher(
            scheduler=scheduler,
            job_repository=job_repository,
            enable_job_timeout_detection=enable_job_timeout_detection,
            now_provider=now_provider,
        )

    @staticmethod
    def _error(code, message):
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }

    def ask(self, user_message):
        if (
            not isinstance(user_message, str)
            or not user_message.strip()
        ):
            return self._error(
                "INVALID_MESSAGE",
                "User message must be non-empty",
            )

        try:
            decision = self._llm.decide(user_message)
        except Exception:
            return self._error(
                "LLM_DECISION_FAILED",
                "LLM decision failed",
            )

        if not isinstance(decision, dict):
            return self._error(
                "INVALID_DECISION",
                "LLM returned an invalid decision",
            )

        decision_type = decision.get("type")

        if decision_type == "DIRECT_ANSWER":
            if set(decision) != {"type", "answer"}:
                return self._error(
                    "INVALID_DECISION",
                    "Unexpected direct answer fields",
                )

            answer = decision.get("answer")

            if not isinstance(answer, str):
                return self._error(
                    "INVALID_DECISION",
                    "Direct answer must be a string",
                )

            return {
                "ok": True,
                "type": "DIRECT_ANSWER",
                "answer": answer,
            }

        if decision_type == "TOOL_CALL":
            if set(decision) != {
                "type", "tool_name", "arguments"
            }:
                return self._error(
                    "INVALID_DECISION",
                    "Unexpected tool call fields",
                )

            tool_name = decision["tool_name"]
            arguments = decision["arguments"]

            if not isinstance(arguments, str):
                return self._error(
                    "INVALID_DECISION",
                    "Tool arguments must be JSON text",
                )

            result = self._dispatcher.dispatch(
                tool_name=tool_name,
                arguments_json=arguments,
            )

            response = {
                "ok": result["ok"],
                "type": "TOOL_RESULT",
                "tool_name": tool_name,
                "result": result,
            }

            if (
                    result["ok"]
                    and tool_name == "get_recent_abnormal_jobs"
            ):
                try:
                    tool_result = result["result"]

                    summary = build_abnormal_summary(tool_result)
                    audit = build_job_monitoring_audit(tool_result)
                    
                    # 为本次逻辑审计事件分配唯一标识
                    audit["event_id"] = f"EVT-{uuid.uuid4().hex}"

                except (ValueError, KeyError, TypeError):
                    return self._error(
                        "INVALID_JOB_SUMMARY",
                        "JOB result metadata is inconsistent",
                    )

                response["summary"] = summary
                response["audit"] = audit

                if self._audit_recorder is not None:

                    try:
                        recording_result = self._audit_recorder.record(audit)

                        if recording_result in ("QUEUED", "REJECTED"):
                            response["audit_recording_status"] = recording_result
                        else:
                            # 保持原有同步 Recorder 的成功语义
                            response["audit_recording_status"] = "SUCCESS"

                    except Exception:
                        response["audit_recording_status"] = "FAILED"

            return response

        return self._error(
            "INVALID_DECISION",
            "Unsupported LLM decision type",
        )
