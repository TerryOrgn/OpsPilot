
from datetime import datetime, timedelta
from unittest.mock import patch

import job_monitor
from alert_manager import save_alert, resolve_alert


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    now = datetime.now()
    start = now - timedelta(minutes=40)

    job = {
        "EXECUTION_ID": "TEST-E2E-001",
        "JOB_NAME": "TestJob",
        "STATUS": "RUNNING",
        "START_TIME": start,
        "END_TIME": None,
        "ERROR_MESSAGE": None,
    }

    active_alerts = set()
    events = []

    def fake_save_alert(job, alert_type, level, message):
        key = (job["EXECUTION_ID"], alert_type)
        if key in active_alerts:
            event_type = "DUPLICATE"
        else:
            active_alerts.add(key)
            event_type = "CREATED"

        events.append(("SAVE", alert_type, event_type))
        return {"event_type": event_type}

    def fake_resolve(execution_id, alert_type, reason):
        key = (execution_id, alert_type)

        # print("[DEBUG] RESOLVE_CALLED:", key)

        if key in active_alerts:
            active_alerts.remove(key)
            return True

        return False

    with patch.object(job_monitor, "save_alert", fake_save_alert), \
         patch.object(job_monitor, "resolve_alert", fake_resolve):

        # 1. RUNNING timeout
        alert = job_monitor.detect_job_alert(job)
        check("RUNNING_TIMEOUT", alert["type"] == "JOB_TIMEOUT")
        fake_save_alert(
            job, alert["type"], alert["level"], alert["message"]
        )

        # 2. Duplicate scan
        alert = job_monitor.detect_job_alert(job)
        result = fake_save_alert(
            job, alert["type"], alert["level"], alert["message"]
        )
        check("DUPLICATE_SUPPRESSED",
              result["event_type"] == "DUPLICATE")

        # 3. FAILED takes over TIMEOUT
        job["STATUS"] = "FAILED"
        job["END_TIME"] = now
        job["ERROR_MESSAGE"] = "Database connection timeout"

        alert = job_monitor.detect_job_alert(job)
        check("FAILED_DETECTED", alert["type"] == "JOB_FAILED")
        fake_save_alert(
            job, alert["type"], alert["level"], alert["message"]
        )
        job_monitor.auto_resolve_job_alerts(job)

        check(
            "TIMEOUT_RESOLVED_ON_FAILURE",
            (job["EXECUTION_ID"], "JOB_TIMEOUT") not in active_alerts,
        )
        check(
            "FAILED_ALERT_ACTIVE",
            (job["EXECUTION_ID"], "JOB_FAILED") in active_alerts,
        )

        # 4. SUCCESS
        job["STATUS"] = "SUCCESS"
        job["END_TIME"] = start + timedelta(minutes=10)

        alert = job_monitor.detect_job_alert(job)
        check("SUCCESS_NO_ALERT", alert is None)

        job_monitor.auto_resolve_job_alerts(job)

        check(
            "FAILED_RESOLVED_ON_SUCCESS",
            (job["EXECUTION_ID"], "JOB_FAILED") not in active_alerts,
        )

        check(
            "TIMEOUT_NOT_ACTIVE_AFTER_SUCCESS",
            (job["EXECUTION_ID"], "JOB_TIMEOUT") not in active_alerts,
        )

        check(
            "ALL_ALERTS_RESOLVED",
            len(active_alerts) == 0,
        )


    # SUCCESS but duration exceeds the threshold.
    slow_job = {
        "EXECUTION_ID": "TEST-E2E-SLOW",
        "JOB_NAME": "SlowSuccessJob",
        "STATUS": "SUCCESS",
        "START_TIME": datetime.now() - timedelta(minutes=40),
        "END_TIME": datetime.now(),
        "ERROR_MESSAGE": None,
    }

    active_alerts = set()

    def fake_resolve(execution_id, alert_type, reason):
        key = (execution_id, alert_type)
        if key in active_alerts:
            active_alerts.remove(key)
            return True
        return False

    active_alerts.add(("TEST-E2E-SLOW", "JOB_FAILED"))

    with patch.object(job_monitor, "resolve_alert", fake_resolve):
        alert = job_monitor.detect_job_alert(slow_job)

        check(
            "SLOW_SUCCESS_TIMEOUT_DETECTED",
            alert is not None and alert["type"] == "JOB_TIMEOUT",
        )

        # Simulate persisting the detected timeout alert.
        active_alerts.add(("TEST-E2E-SLOW", "JOB_TIMEOUT"))

        job_monitor.auto_resolve_job_alerts(slow_job)

        # print("[DEBUG] ACTIVE_ALERTS_AFTER_SLOW_SUCCESS:", active_alerts)

        check(
            "SLOW_SUCCESS_FAILED_RESOLVED",
            ("TEST-E2E-SLOW", "JOB_FAILED") not in active_alerts,
        )

        check(
            "SLOW_SUCCESS_TIMEOUT_PRESERVED",
            ("TEST-E2E-SLOW", "JOB_TIMEOUT") in active_alerts,
        )


    print("[TEST] ALL PASS: JOB Lifecycle Baseline")


if __name__ == "__main__":
    main()
