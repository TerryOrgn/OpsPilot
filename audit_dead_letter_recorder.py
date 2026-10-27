
import json
import os
from pathlib import Path
from threading import Lock


class DeadLetterRecorder:
    def __init__(self, file_path):
        self._file_path = Path(file_path)
        self._lock = Lock()

    def record(self, audit, failure_result):
        if not isinstance(audit, dict):
            raise ValueError("audit must be a dict")

        if not isinstance(failure_result, dict):
            raise ValueError(
                "failure_result must be a dict"
            )

        event_id = audit.get("event_id")

        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        if failure_result.get("status") != "FAILED":
            raise ValueError(
                "Only FAILED results can be recorded"
            )

        if failure_result.get("event_id") != event_id:
            raise ValueError(
                "event_id mismatch"
            )

        entry = {
            "event_id": event_id,
            "audit": dict(audit),
            "failure": dict(failure_result),
        }

        # 先序列化，避免格式错误时写入半条 JSON
        line = json.dumps(
            entry,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"

        with self._lock:
            self._file_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self._file_path.open(
                "a",
                encoding="utf-8",
            ) as file:
                file.write(line)
                file.flush()
                os.fsync(file.fileno())

        return {
            "status": "RECORDED",
            "event_id": event_id,
        }
