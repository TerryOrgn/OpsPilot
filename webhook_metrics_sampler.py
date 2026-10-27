
from threading import Lock

from webhook_metrics import webhook_metrics
from webhook_metrics_window import (
    METRIC_KEYS,
    calculate_window_error_rate,
)


class MetricsWindowSampler:

    def __init__(self, metrics=None):
        self._metrics = (
            metrics if metrics is not None
            else webhook_metrics
        )
        self._previous = None
        self._lock = Lock()

    def sample(self):
        with self._lock:
            current = self._metrics.snapshot()

            # 首次采样：建立基线
            if self._previous is None:
                self._validate(current)
                self._previous = current.copy()

                return {
                    "status": "BASELINE",
                    "window": None,
                }

            # 正常计算窗口指标
            try:
                window = calculate_window_error_rate(
                    self._previous,
                    current,
                )
            except ValueError as exc:
                # 仅计数器减少时重建基线
                if str(exc).startswith("Counter decreased:"):
                    self._previous = current.copy()

                    return {
                        "status": "RESET",
                        "window": None,
                    }

                raise

            self._previous = current.copy()

            return {
                "status": "OK",
                "window": window,
            }

    @staticmethod
    def _validate(snapshot):
        for key in METRIC_KEYS:
            value = snapshot[key]

            if type(value) is not int or value < 0:
                raise ValueError(
                    f"Invalid metric value: {key}"
                )
