
from threading import Lock


class WebhookMetrics:
    def __init__(self):
        self._lock = Lock()
        self._counters = {
            "processed_total": 0,
            "duplicate_total": 0,
            "conflict_total": 0,
            "error_total": 0,
        }

    def record(self, result):
        mapping = {
            "PROCESSED": "processed_total",
            "DUPLICATE": "duplicate_total",
            "CONFLICT": "conflict_total",
            "ERROR": "error_total",
        }

        if result not in mapping:
            raise ValueError(
                f"Unknown webhook result: {result}"
            )

        with self._lock:
            self._counters[mapping[result]] += 1

    def snapshot(self):
        with self._lock:
            return self._counters.copy()

    def reset(self):
        with self._lock:
            for key in self._counters:
                self._counters[key] = 0


webhook_metrics = WebhookMetrics()
