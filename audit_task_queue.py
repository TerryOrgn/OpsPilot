
from queue import Queue, Full, Empty
from threading import Lock
import time


class BoundedAuditQueue:
    def __init__(self, maxsize=100):
        if (
            isinstance(maxsize, bool)
            or not isinstance(maxsize, int)
            or maxsize < 1
        ):
            raise ValueError(
                "maxsize must be a positive integer"
            )

        self._queue = Queue(maxsize=maxsize)
        self._lock = Lock()
        self._closed = False

    def submit(self, audit):
        if not isinstance(audit, dict):
            raise ValueError("audit must be a dictionary")

        event_id = audit.get("event_id")

        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or len(event_id) > 64
        ):
            raise ValueError("valid event_id is required")

        with self._lock:
            if self._closed:
                return {
                    "status": "REJECTED",
                    "reason": "QUEUE_CLOSED",
                    "event_id": event_id,
                }

            try:
                self._queue.put_nowait(dict(audit))
            except Full:
                return {
                    "status": "REJECTED",
                    "reason": "QUEUE_FULL",
                    "event_id": event_id,
                }

        return {
            "status": "QUEUED",
            "event_id": event_id,
        }

    def get_nowait(self):
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def task_done(self):
        self._queue.task_done()

    def size(self):
        return self._queue.qsize()

    def close(self):
        with self._lock:
            self._closed = True

    def join(self):
        self._queue.join()


    def wait_until_done(self, timeout=2.0):
        """
        等待队列所有未完成任务结束。

        True: 未完成任务数归零
        False: 超时后仍有任务未完成
        """
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not (0 <= timeout < float("inf"))
        ):
            raise ValueError(
                "timeout must be a finite non-negative number"
            )

        deadline = time.monotonic() + timeout

        # 使用 Queue 自带的条件变量及未完成任务计数
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    return False

                self._queue.all_tasks_done.wait(
                    timeout=remaining
                )

            return True

