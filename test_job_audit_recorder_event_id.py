
import json

from job_audit_recorder import JobAuditRecorder


class FakeSink:
    def __init__(self):
        self.payloads = []

    def write(self, payload):
        self.payloads.append(json.loads(payload))


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def expect_invalid(name, audit):
    sink = FakeSink()
    recorder = JobAuditRecorder(sink)

    try:
        recorder.record(audit)
    except (ValueError, TypeError):
        check(name, len(sink.payloads) == 0)
    else:
        raise AssertionError(
            f"{name}: invalid event_id was accepted"
        )


base_audit = {
    "event": "JOB_MONITORING_SUMMARY",
    "tool_name": "get_recent_abnormal_jobs",
    "total_abnormal_count": 0,
    "returned_count": 0,
    "truncated": False,
    "summary_status": "SUCCESS",
}

# 1. 合法 Event ID
sink = FakeSink()
recorder = JobAuditRecorder(sink)

audit = {
    **base_audit,
    "request_id": "REQ-BO5E-001",
    "event_id": "EVT-BO5E-001",
}

check(
    "VALID_EVENT_ID",
    recorder.record(audit) is True,
)

check(
    "EVENT_ID_PRESERVED",
    sink.payloads[0]["event_id"] == "EVT-BO5E-001",
)

check(
    "REQUEST_ID_PRESERVED",
    sink.payloads[0]["request_id"] == "REQ-BO5E-001",
)

# 2. 无 Event ID 的旧版审计兼容
legacy_sink = FakeSink()
legacy_recorder = JobAuditRecorder(legacy_sink)

check(
    "LEGACY_COMPATIBLE",
    legacy_recorder.record(base_audit) is True,
)

check(
    "LEGACY_NO_EVENT_ID",
    "event_id" not in legacy_sink.payloads[0],
)

# 3. 非法 Event ID
expect_invalid(
    "EMPTY_EVENT_ID_REJECTED",
    {**base_audit, "event_id": ""},
)

expect_invalid(
    "WHITESPACE_EVENT_ID_REJECTED",
    {**base_audit, "event_id": "   "},
)

expect_invalid(
    "NON_STRING_EVENT_ID_REJECTED",
    {**base_audit, "event_id": 123},
)

expect_invalid(
    "NULL_EVENT_ID_REJECTED",
    {**base_audit, "event_id": None},
)

expect_invalid(
    "TOO_LONG_EVENT_ID_REJECTED",
    {**base_audit, "event_id": "E" * 65},
)

check(
    "MAX_LENGTH_EVENT_ID_ACCEPTED",
    JobAuditRecorder(FakeSink()).record(
        {**base_audit, "event_id": "E" * 64}
    ) is True,
)

print("[TEST] ALL PASS: Recorder Event ID")
