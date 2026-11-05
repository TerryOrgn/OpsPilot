
from audit_replay_lock_review import ReplayLockReview


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    locks = [
        {
            "event_id": "EVT-001",
            "status": "STALE_SUSPECTED",
        },
        {
            "event_id": "EVT-002",
            "status": "AGE_UNKNOWN",
        },
        {
            "event_id": "EVT-003",
            "status": "ACTIVE",
        },
    ]

    audits = [
        {"event_id": "EVT-001", "status": "STARTED"},
        {"event_id": "EVT-002", "status": "STARTED"},
        {"event_id": "EVT-002", "status": "SUCCESS"},
    ]

    reports = ReplayLockReview().build(locks, audits)

    by_id = {
        item["event_id"]: item
        for item in reports
    }

    check("THREE_REPORTS", len(reports) == 3)

    check(
        "STALE_LOCK_IDENTIFIED",
        by_id["EVT-001"]["lock_status"]
        == "STALE_SUSPECTED",
    )

    check(
        "STARTED_WITHOUT_TERMINAL",
        by_id["EVT-001"]["last_audit_status"]
        == "STARTED"
        and not by_id["EVT-001"]["terminal_audit_found"],
    )

    check(
        "TERMINAL_AUDIT_FOUND",
        by_id["EVT-002"]["last_audit_status"]
        == "SUCCESS"
        and by_id["EVT-002"]["terminal_audit_found"],
    )

    check(
        "MISSING_AUDIT_REPORTED",
        by_id["EVT-003"]["last_audit_status"] is None
        and not by_id["EVT-003"]["terminal_audit_found"],
    )

    check(
        "ALL_REQUIRE_MANUAL_REVIEW",
        all(
            item["recommendation"]
            == "MANUAL_REVIEW_REQUIRED"
            for item in reports
        ),
    )

    check(
        "INPUTS_UNCHANGED",
        len(locks) == 3 and len(audits) == 3,
    )

    print("[TEST] ALL PASS: Replay Lock Review")


if __name__ == "__main__":
    main()
