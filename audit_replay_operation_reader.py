
import json
from pathlib import Path


class ReplayOperationReader:
    def __init__(self, file_path):
        self._file_path = Path(file_path)

    def read_all(self):
        if not self._file_path.exists():
            raise FileNotFoundError(
                f"Replay audit file not found: {self._file_path}"
            )

        records = []

        with self._file_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    raise ValueError(
                        f"Empty audit line: {line_number}"
                    )

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at line {line_number}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid audit object at line {line_number}"
                    )

                if record.get("action") != "DEAD_LETTER_REPLAY":
                    raise ValueError(
                        f"Invalid action at line {line_number}"
                    )

                if not isinstance(record.get("event_id"), str) \
                        or not record["event_id"].strip():
                    raise ValueError(
                        f"Invalid event_id at line {line_number}"
                    )

                if record.get("status") not in {
                    "REJECTED", "STARTED", "SUCCESS", "FAILED"
                }:
                    raise ValueError(
                        f"Invalid status at line {line_number}"
                    )

                attempt_id = record.get("replay_attempt_id")
                if attempt_id is not None and (
                    not isinstance(attempt_id, str)
                    or not attempt_id.strip()
                ):
                    raise ValueError(
                        f"Invalid replay_attempt_id at line {line_number}"
                    )

                records.append(record)

        return records
