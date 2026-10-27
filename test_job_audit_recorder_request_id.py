
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


base_audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 15,
    "returned_count": 10,
    "truncated": True,
    "summary_status": "SUCCESS",
}

sink = FakeSink()
recorder = JobAuditRecorder(sink)


# Case 1: New audit with request_id
audit_with_id = {
    **base_audit,
    "request_id": "REQ-BN3-001",
}

check(
    "REQUEST_ID_RECORD_SUCCESS",
    recorder.record(audit_with_id) is True,
)

saved = json.loads(sink.records[-1])

check(
    "REQUEST_ID_PRESERVED",
    saved["request_id"] == "REQ-BN3-001",
)


# Case 2: Legacy audit without request_id
check(
    "LEGACY_AUDIT_COMPATIBLE",
    recorder.record(base_audit) is True,
)

legacy_saved = json.loads(sink.records[-1])

check(
    "LEGACY_NO_REQUEST_ID",
    "request_id" not in legacy_saved,
)


# Case 3: Invalid request IDs
before = len(sink.records)

check(
    "EMPTY_REQUEST_ID_REJECTED",
    rejected(
        recorder,
        {**base_audit, "request_id": ""},
    ),
)

check(
    "WHITESPACE_REQUEST_ID_REJECTED",
    rejected(
        recorder,
        {**base_audit, "request_id": "   "},
    ),
)

check(
    "NON_STRING_REQUEST_ID_REJECTED",
    rejected(
        recorder,
        {**base_audit, "request_id": 123},
    ),
)

check(
    "NONE_REQUEST_ID_REJECTED",
    rejected(
        recorder,
        {**base_audit, "request_id": None},
    ),
)


# Case 4: Extra fields still rejected
check(
    "EXTRA_FIELD_REJECTED",
    rejected(
        recorder,
        {
            **audit_with_id,
            "job_name": "SensitiveJob",
        },
    ),
)

check(
    "INVALID_EVENTS_NOT_WRITTEN",
    len(sink.records) == before,
)

check(
    "VALID_RECORD_COUNT",
    len(sink.records) == 2,
)

print("[TEST] ALL PASS: Job Audit Recorder Request ID")
