
from threading import Event, Thread


class AuditWorker:

    def __init__(
            self,
            audit_queue,
            retry_service,
            poll_interval=0.05,
            dead_letter_recorder=None,
    ):
        if not callable(
            getattr(audit_queue, "get_nowait", None)
        ):
            raise ValueError(
                "audit_queue must provide get_nowait()"
            )

        if not callable(
            getattr(audit_queue, "task_done", None)
        ):
            raise ValueError(
                "audit_queue must provide task_done()"
            )

        if not callable(
            getattr(retry_service, "execute", None)
        ):
            raise ValueError(
                "retry_service must provide execute()"
            )

        if (
            isinstance(poll_interval, bool)
            or not isinstance(poll_interval, (int, float))
            or not (0 < poll_interval < float("inf"))
        ):
            raise ValueError(
                "poll_interval must be a finite positive number"
            )

        self._queue = audit_queue
        self._dead_letter_recorder = dead_letter_recorder
        self._retry_service = retry_service
        self._poll_interval = poll_interval

        self._stop_event = Event()
        self._thread = None

        # 本轮仅用于测试与诊断，不作为持久化记录
        self.results = []

    def start(self):
        if self._thread is not None:
            raise RuntimeError(
                "Worker already started"
            )

        self._stop_event.clear()

        self._thread = Thread(
            target=self._run,
            name="OpsPilotAuditWorker",
            daemon=True,
        )

        self._thread.start()

    def _run(self):
        while not self._stop_event.is_set():
            audit = self._queue.get_nowait()

            if audit is None:
                self._stop_event.wait(
                    self._poll_interval
                )
                continue

            try:

                result = self._retry_service.execute(audit)
                result = self._save_dead_letter(audit, result)
                self.results.append(result)

            except Exception as exc:
                # 不记录完整异常消息，避免敏感信息泄露
                result = {
                    "status": "FAILED",
                    "event_id": audit.get("event_id"),
                    "last_error_type": type(exc).__name__,
                }

                result = self._save_dead_letter(audit, result)
                self.results.append(result)

            finally:
                self._queue.task_done()

    def stop(self, timeout=2.0):
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout)

        return (
            self._thread is None
            or not self._thread.is_alive()
        )

    def _save_dead_letter(self, audit, result):
        if result.get("status") != "FAILED":
            return result

        if self._dead_letter_recorder is None:
            result["dead_letter_status"] = "NOT_CONFIGURED"
            return result

        try:
            self._dead_letter_recorder.record(audit, result)
            result["dead_letter_status"] = "RECORDED"

        except Exception as exc:
            result["dead_letter_status"] = "FAILED"
            result["dead_letter_error_type"] = type(exc).__name__

        return result



