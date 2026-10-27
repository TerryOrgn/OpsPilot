
from audit_dead_letter_reader import DeadLetterReader


class DeadLetterReplayPreview:
    RETRYABLE_ERROR_TYPES = {"ConnectionError"}

    def __init__(self, file_path):
        self._reader = DeadLetterReader(file_path)

    def build(self):
        records = self._reader.read_all()
        preview = []

        for record in records:
            failure = record["failure"]
            error_type = failure.get("last_error_type")
            eligible = error_type in self.RETRYABLE_ERROR_TYPES

            preview.append({
                "event_id": record["event_id"],
                "failure_type": error_type,
                "replay_eligible": eligible,
                "reason": (
                    "RETRYABLE_FAILURE"
                    if eligible
                    else "MANUAL_REVIEW_REQUIRED"
                ),
            })

        return preview
