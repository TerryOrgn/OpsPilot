
import time

from audit_retry_policy import is_retryable_database_error
from audit_backoff_policy import calculate_backoff


class AuditRetryService:

    def __init__(
        self,
        recorder,
        max_attempts=2,
        base_delay=1.0,
        max_delay=8.0,
        sleep_fn=None,
    ):
        if not callable(getattr(recorder, "record", None)):
            raise ValueError("recorder must provide record()")

        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise ValueError(
                "max_attempts must be a positive integer"
            )

        # 复用已有的退避参数校验
        calculate_backoff(
            failure_count=1,
            base_delay=base_delay,
            max_delay=max_delay,
        )

        if sleep_fn is not None and not callable(sleep_fn):
            raise ValueError("sleep_fn must be callable")

        self._recorder = recorder
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep_fn = (
            time.sleep if sleep_fn is None else sleep_fn
        )

    def execute(self, audit):
        if not isinstance(audit, dict):
            raise ValueError("audit must be a dictionary")

        event_id = audit.get("event_id")

        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or len(event_id) > 64
        ):
            raise ValueError("valid event_id is required")

        fixed_audit = dict(audit)

        for attempt in range(1, self._max_attempts + 1):
            try:
                self._recorder.record(dict(fixed_audit))

                return {
                    "status": "SUCCESS",
                    "event_id": event_id,
                    "attempts": attempt,
                }

            except Exception as exc:
                if not is_retryable_database_error(exc):
                    raise

                if attempt == self._max_attempts:
                    error_code = getattr(exc, "errno", None)

                    return {
                        "status": "FAILED",
                        "event_id": event_id,
                        "attempts": attempt,
                        "last_error_type": type(exc).__name__,
                        "last_error_code": (
                            error_code
                            if isinstance(error_code, int)
                               and not isinstance(error_code, bool)
                            else None
                        ),
                    }

                delay = calculate_backoff(
                    failure_count=attempt,
                    base_delay=self._base_delay,
                    max_delay=self._max_delay,
                )

                self._sleep_fn(delay)
