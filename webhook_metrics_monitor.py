
from threading import Lock

from webhook_metrics_sampler import MetricsWindowSampler
from webhook_metrics_threshold import evaluate_error_rate


class WebhookMetricsMonitor:

    def __init__(
        self,
        metrics=None,
        min_requests=10,
        error_threshold=20.0,
    ):
        self._sampler = MetricsWindowSampler(metrics)
        self._min_requests = min_requests
        self._error_threshold = error_threshold
        self._lock = Lock()

    def evaluate(self):
        with self._lock:
            sampled = self._sampler.sample()

            # 首次采样或计数器重置
            if sampled["status"] in ("BASELINE", "RESET"):
                return {
                    "status": sampled["status"],
                    "window": None,
                }

            window = sampled["window"]

            evaluation = evaluate_error_rate(
                window,
                min_requests=self._min_requests,
                error_threshold=self._error_threshold,
            )

            return {
                "status": evaluation["status"],
                "window": window,
            }
