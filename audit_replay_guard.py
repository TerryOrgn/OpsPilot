
from threading import Lock


class ReplayConcurrencyGuard:
    def __init__(self):
        self._lock = Lock()
        self._active_event_ids = set()

    def try_acquire(self, event_id):
        with self._lock:
            if event_id in self._active_event_ids:
                return False

            self._active_event_ids.add(event_id)
            return True

    def release(self, event_id):
        with self._lock:
            self._active_event_ids.discard(event_id)
