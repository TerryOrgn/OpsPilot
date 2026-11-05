
from audit_replay_attempt_matcher import ReplayAttemptMatcher


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def audit(attempt_id, status, event_id="EVT-001"):
    return {
        "action": "DEAD_LETTER_REPLAY",
        "event_id": event_id,
        "replay_attempt_id": attempt_id,
        "status": status,
    }


def main():
    match = ReplayAttemptMatcher.match
    lock = {
        "event_id": "EVT-001",
        "replay_attempt_id": "ATTEMPT-B",
    }

    records = [
        audit("ATTEMPT-A", "STARTED"),
        audit("ATTEMPT-A", "SUCCESS"),
        audit("ATTEMPT-B", "STARTED"),
    ]

    result = match(lock, records)

    check("CURRENT_ATTEMPT_INCOMPLETE",
          result["status"] == "ATTEMPT_INCOMPLETE")
    check("HISTORICAL_SUCCESS_IGNORED",
          len(result["records"]) == 1)

    result = match(lock, records + [
        audit("ATTEMPT-B", "SUCCESS"),
    ])
    check("CURRENT_ATTEMPT_SUCCESS",
          result["status"] == "ATTEMPT_SUCCESS")

    result = match(lock, [
        audit("ATTEMPT-B", "STARTED"),
        audit("ATTEMPT-B", "FAILED"),
    ])
    check("CURRENT_ATTEMPT_FAILED",
          result["status"] == "ATTEMPT_FAILED")

    result = match(lock, [
        audit("ATTEMPT-A", "SUCCESS"),
    ])
    check("MISSING_CURRENT_AUDIT",
          result["reason"] == "ATTEMPT_AUDIT_NOT_FOUND")

    result = match({
        "event_id": "EVT-001",
        "replay_attempt_id": None,
    }, records)
    check("LEGACY_LOCK_UNCERTAIN",
          result["status"] == "CORRELATION_UNCERTAIN")

    result = match(lock, [
        audit("ATTEMPT-B", "SUCCESS"),
    ])
    check("TERMINAL_WITHOUT_STARTED_REJECTED",
          result["reason"] == "INVALID_AUDIT_SEQUENCE")

    result = match(lock, [
        audit("ATTEMPT-B", "STARTED"),
        audit("ATTEMPT-B", "STARTED"),
    ])
    check("DUPLICATE_STARTED_REJECTED",
          result["reason"] == "INVALID_AUDIT_SEQUENCE")

    result = match(lock, [
        audit("ATTEMPT-B", "STARTED"),
        audit("ATTEMPT-B", "SUCCESS"),
        audit("ATTEMPT-B", "FAILED"),
    ])
    check("MULTIPLE_TERMINALS_REJECTED",
          result["reason"] == "INVALID_AUDIT_SEQUENCE")

    result = match(lock, [
        audit("ATTEMPT-B", "STARTED", "EVT-OTHER"),
    ])
    check("OTHER_EVENT_IGNORED",
          result["reason"] == "ATTEMPT_AUDIT_NOT_FOUND")

    print("[TEST] ALL PASS: Replay Attempt Matcher")


if __name__ == "__main__":
    main()
