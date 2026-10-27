
import json
from pathlib import Path


class DeadLetterReader:
    def __init__(self, file_path):
        self._file_path = Path(file_path)

    def read_all(self):
        records = []

        with self._file_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON at line {line_number}"
                    ) from exc

                if not isinstance(record, dict):
                    raise ValueError(
                        f"Invalid record at line {line_number}"
                    )

                event_id = record.get("event_id")
                audit = record.get("audit")
                failure = record.get("failure")

                if not isinstance(event_id, str) or not event_id.strip():
                    raise ValueError(
                        f"Invalid event_id at line {line_number}"
                    )

                if not isinstance(audit, dict) or not isinstance(failure, dict):
                    raise ValueError(
                        f"Invalid audit/failure at line {line_number}"
                    )

                if (
                    audit.get("event_id") != event_id
                    or failure.get("event_id") != event_id
                    or failure.get("status") != "FAILED"
                ):
                    raise ValueError(
                        f"Inconsistent dead letter at line {line_number}"
                    )

                records.append(record)

        return records
