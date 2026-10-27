
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class ReplayOperationRecorder:
    def __init__(self, file_path):
        self._file_path = Path(file_path)
        self._lock = threading.Lock()

    def record(self, operation):
        if not isinstance(operation, dict):
            raise ValueError("operation must be a dictionary")

        if operation.get("action") != "DEAD_LETTER_REPLAY":
            raise ValueError("Invalid replay action")

        event_id = operation.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        entry = dict(operation)
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()

        line = json.dumps(entry, ensure_ascii=False)

        with self._lock:
            with self._file_path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
                file.flush()
                os.fsync(file.fileno())

        return {
            "status": "RECORDED",
            "event_id": event_id,
        }
