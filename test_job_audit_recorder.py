
import json

from job_audit_recorder import JobAuditRecorder


class FakeSink:
    def __init__(self):
        self.records = []

    def write(self, payload):
        self.records.append(payload)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def rejected(recorder, audit):
    try:
        recorder.record(audit)
    except ValueError:
        return True
    return False


sink = FakeSink()
recorder = JobAuditRecorder(sink)

audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 15,
    "returned_count": 10,
    "truncated": True,
    "summary_status": "SUCCESS",
}

check(
    "RECORD_SUCCESS",
    recorder.record(audit) is True,
)

check(
    "SINK_RECEIVED",
    len(sink.records) == 1,
)

saved = json.loads(sink.records[0])

check(
    "JSON_VALID",
    isinstance(saved, dict),
)

check(
    "COUNTS_PRESERVED",
    saved["total_abnormal_count"] == 15
    and saved["returned_count"] == 10,
)

check(
    "TRUNCATED_PRESERVED",
    saved["truncated"] is True,
)

check(
    "NO_JOB_DETAILS",
    "jobs" not in saved
    and "execution_id" not in saved
    and "job_name" not in saved,
)

before = len(sink.records)

check(
    "INVALID_COUNT_REJECTED",
    rejected(
        recorder,
        {**audit, "total_abnormal_count": -1},
    ),
)

check(
    "BOOLEAN_COUNT_REJECTED",
    rejected(
        recorder,
        {**audit, "returned_count": True},
    ),
)

check(
    "INCONSISTENT_TRUNCATED_REJECTED",
    rejected(
        recorder,
        {**audit, "truncated": False},
    ),
)

check(
    "EXTRA_FIELDS_REJECTED",
    rejected(
        recorder,
        {**audit, "job_name": "SensitiveJob"},
    ),
)

check(
    "INVALID_RECORDS_NOT_WRITTEN",
    len(sink.records) == before,
)


class FailingSink:
    def write(self, payload):
        raise OSError("simulated sink failure")


failing_recorder = JobAuditRecorder(FailingSink())

try:
    failing_recorder.record(audit)
except OSError:
    sink_failure_propagated = True
else:
    sink_failure_propagated = False

check(
    "SINK_FAILURE_PROPAGATED",
    sink_failure_propagated,
)

print("[TEST] SAVED=", sink.records[0])
print("[TEST] ALL PASS: Job Audit Recorder")
