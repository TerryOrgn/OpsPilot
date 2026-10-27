
from threading import Lock

from webhook_metrics_monitor import WebhookMetricsMonitor
from webhook_metrics_alert_state import WebhookMetricsAlertState


class WebhookMetricsAlertPipeline:

    def __init__(
        self,
        metrics=None,
        min_requests=10,
        error_threshold=20.0,
    ):
        self._monitor = WebhookMetricsMonitor(
            metrics=metrics,
            min_requests=min_requests,
            error_threshold=error_threshold,
        )

        self._alert_state = WebhookMetricsAlertState()
        self._lock = Lock()

    def run(self):
        with self._lock:
            evaluation = self._monitor.evaluate()

            transition = self._alert_state.update(
                evaluation["status"]
            )

            return {
                "monitor_status": evaluation["status"],
                "event": transition["event"],
                "previous_state": transition["previous_state"],
                "current_state": transition["current_state"],
                "window": evaluation["window"],
            }

    def current_alert_state(self):
        with self._lock:
            return self._alert_state.current_state()
