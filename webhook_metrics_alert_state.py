
from threading import Lock


class WebhookMetricsAlertState:

    def __init__(self):
        self._state = "NORMAL"
        self._lock = Lock()

    def update(self, monitor_status: str) -> dict:
        valid_statuses = {
            "ALERT",
            "OK",
            "INSUFFICIENT_DATA",
            "BASELINE",
            "RESET",
        }

        if monitor_status not in valid_statuses:
            raise ValueError(
                f"Invalid monitor status: {monitor_status}"
            )

        with self._lock:
            previous_state = self._state

            if monitor_status == "ALERT":
                if self._state == "NORMAL":
                    self._state = "FIRING"
                    event = "NEW_ALERT"
                else:
                    event = "DUPLICATE"

            elif monitor_status == "OK":
                if self._state == "FIRING":
                    self._state = "NORMAL"
                    event = "RESOLVED"
                else:
                    event = "NO_CHANGE"

            else:
                # 数据不足、首次采样、计数器重置
                # 均不改变告警状态
                event = "NO_CHANGE"

            return {
                "event": event,
                "previous_state": previous_state,
                "current_state": self._state,
            }

    def current_state(self) -> str:
        with self._lock:
            return self._state
