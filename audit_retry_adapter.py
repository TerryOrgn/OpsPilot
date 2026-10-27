
class AuditRetryExhaustedError(Exception):
    """审计重试耗尽。"""


class AuditRetryAdapter:
    def __init__(self, retry_service):
        if not callable(
            getattr(retry_service, "execute", None)
        ):
            raise ValueError(
                "retry_service must provide execute()"
            )

        self._retry_service = retry_service

    def record(self, audit):
        result = self._retry_service.execute(audit)

        if result.get("status") == "SUCCESS":
            return True

        if result.get("status") == "FAILED":
            # 不拼接完整数据库异常信息
            raise AuditRetryExhaustedError(
                "Audit retry exhausted"
            )

        raise ValueError(
            "Unexpected audit retry result"
        )
