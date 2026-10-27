
from datetime import datetime, timedelta

from job_timeout_detector import detect_job_status


NOW = datetime(2026, 10, 24, 12, 0, 0)


def make_job(status, minutes_ago):
    return {
        "status": status,
        "updated_at": NOW - timedelta(
            minutes=minutes_ago
        ),
    }


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


check(
    "RUNNING_20_MIN",
    detect_job_status(
        make_job("RUNNING", 20), NOW
    ) == "RUNNING",
)

check(
    "RUNNING_29_MIN",
    detect_job_status(
        make_job("RUNNING", 29), NOW
    ) == "RUNNING",
)

check(
    "RUNNING_30_MIN",
    detect_job_status(
        make_job("RUNNING", 30), NOW
    ) == "TIMEOUT",
)

check(
    "RUNNING_60_MIN",
    detect_job_status(
        make_job("RUNNING", 60), NOW
    ) == "TIMEOUT",
)

check(
    "FAILED_PRESERVED",
    detect_job_status(
        make_job("FAILED", 60), NOW
    ) == "FAILED",
)

check(
    "SUCCESS_PRESERVED",
    detect_job_status(
        make_job("SUCCESS", 60), NOW
    ) == "SUCCESS",
)

check(
    "TIMEOUT_PRESERVED",
    detect_job_status(
        make_job("TIMEOUT", 60), NOW
    ) == "TIMEOUT",
)

check(
    "STRING_DATETIME",
    detect_job_status(
        {
            "status": "RUNNING",
            "updated_at": "2026-10-24T11:00:00",
        },
        NOW,
    ) == "TIMEOUT",
)

try:
    detect_job_status(
        {
            "status": "RUNNING",
            "updated_at": NOW + timedelta(minutes=1),
        },
        NOW,
    )
except ValueError:
    future_rejected = True
else:
    future_rejected = False

check(
    "FUTURE_TIME_REJECTED",
    future_rejected,
)

print("[TEST] ALL PASS: JOB Timeout Detector")
