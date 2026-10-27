
import json
from tempfile import TemporaryDirectory
from pathlib import Path

from audit_dead_letter_recorder import (
    DeadLetterRecorder,
)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


with TemporaryDirectory() as temp_dir:
    file_path = Path(temp_dir) / "audit_dead_letters.jsonl"

    recorder = DeadLetterRecorder(file_path)

    audit = {
        "event_id": "EVT-BO8A-001",
        "event": "JOB_MONITORING_SUMMARY",
        "tool_name": "get_recent_abnormal_jobs",
    }

    failure = {
        "status": "FAILED",
        "event_id": "EVT-BO8A-001",
        "attempts": 2,
        "last_error_type": "ConnectionError",
        "last_error_code": None,
    }

    result = recorder.record(audit, failure)

    check(
        "RECORD_SUCCESS",
        result["status"] == "RECORDED",
    )

    check(
        "FILE_CREATED",
        file_path.exists(),
    )

    lines = file_path.read_text(
        encoding="utf-8"
    ).splitlines()

    check(
        "ONE_LINE_WRITTEN",
        len(lines) == 1,
    )

    entry = json.loads(lines[0])

    check(
        "EVENT_ID_PRESERVED",
        entry["event_id"] == "EVT-BO8A-001",
    )

    check(
        "ORIGINAL_AUDIT_PRESERVED",
        entry["audit"] == audit,
    )

    check(
        "FAILURE_DIAGNOSTICS_PRESERVED",
        entry["failure"] == failure,
    )

    # 第二条记录必须追加，而不是覆盖
    audit2 = {
        **audit,
        "event_id": "EVT-BO8A-002",
    }

    failure2 = {
        **failure,
        "event_id": "EVT-BO8A-002",
    }

    recorder.record(audit2, failure2)

    lines = file_path.read_text(
        encoding="utf-8"
    ).splitlines()

    check(
        "APPEND_NOT_OVERWRITE",
        len(lines) == 2,
    )

    check(
        "SECOND_EVENT_PRESERVED",
        json.loads(lines[1])["event_id"]
        == "EVT-BO8A-002",
    )

    # 不允许将成功事件写入死信文件
    invalid_failure = {
        **failure,
        "status": "SUCCESS",
    }

    try:
        recorder.record(audit, invalid_failure)
        rejected = False
    except ValueError:
        rejected = True

    check(
        "SUCCESS_RESULT_REJECTED",
        rejected,
    )

    # Event ID 不一致必须拒绝
    mismatched_failure = {
        **failure,
        "event_id": "EVT-WRONG",
    }

    try:
        recorder.record(audit, mismatched_failure)
        rejected = False
    except ValueError:
        rejected = True

    check(
        "MISMATCHED_EVENT_ID_REJECTED",
        rejected,
    )

    check(
        "INVALID_RECORDS_NOT_WRITTEN",
        len(
            file_path.read_text(
                encoding="utf-8"
            ).splitlines()
        ) == 2,
    )

print("[TEST] ALL PASS: Dead Letter Recorder")
