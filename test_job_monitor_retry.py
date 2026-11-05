
from datetime import datetime, timedelta
from unittest.mock import patch

import job_monitor
from alert_manager import save_alert, resolve_alert
from db import get_checkpoint, get_incremental_jobs, get_running_jobs, get_job_by_execution_id, update_checkpoint


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def main():
    now = datetime.now()
    old_checkpoint = now - timedelta(hours=1)
    scan_upper_bound = now

    jobs = [
        {
            "EXECUTION_ID": "E2E-RETRY-A",
            "JOB_NAME": "JobA",
            "STATUS": "RUNNING",
            "START_TIME": now - timedelta(minutes=40),
            "END_TIME": None,
            "ERROR_MESSAGE": None,
        },
        {
            "EXECUTION_ID": "E2E-RETRY-B",
            "JOB_NAME": "JobB",
            "STATUS": "FAILED",
            "START_TIME": now - timedelta(minutes=10),
            "END_TIME": now,
            "ERROR_MESSAGE": "Database timeout",
        },
    ]

    checkpoint = old_checkpoint
    checkpoint_updates = []
    active_alerts = set()
    events = []
    fail_once = True

    def fake_get_checkpoint():
        return {"LAST_SCAN_TIME": checkpoint}

    def fake_get_incremental_jobs(last_scan_time, overlap_minutes):
        return jobs, scan_upper_bound

    def fake_get_running_jobs():
        return [jobs[0]]

    def fake_get_job_by_execution_id(execution_id):
        return next(
            job for job in jobs
            if job["EXECUTION_ID"] == execution_id
        )

    def fake_save_alert(job, alert_type, level, message):
        nonlocal fail_once

        execution_id = job["EXECUTION_ID"]
        key = (execution_id, alert_type)

        if execution_id == "E2E-RETRY-B" and fail_once:
            fail_once = False
            raise RuntimeError("Simulated transient persistence failure")

        if key in active_alerts:
            event_type = "DUPLICATE"
        else:
            active_alerts.add(key)
            event_type = "CREATED"

        events.append((execution_id, alert_type, event_type))
        return {"event_type": event_type}

    def fake_resolve_alert(execution_id, alert_type, reason):
        key = (execution_id, alert_type)
        if key in active_alerts:
            active_alerts.remove(key)
            return True
        return False

    def fake_update_checkpoint(value):
        nonlocal checkpoint
        checkpoint = value
        checkpoint_updates.append(value)

    with patch.object(job_monitor, "get_checkpoint", fake_get_checkpoint), \
         patch.object(job_monitor, "get_incremental_jobs",
                      fake_get_incremental_jobs), \
         patch.object(job_monitor, "get_running_jobs",
                      fake_get_running_jobs), \
         patch.object(job_monitor, "get_job_by_execution_id",
                      fake_get_job_by_execution_id), \
         patch.object(job_monitor, "save_alert", fake_save_alert), \
         patch.object(job_monitor, "resolve_alert", fake_resolve_alert), \
         patch.object(job_monitor, "update_checkpoint",
                      fake_update_checkpoint):

        # Round 1: JOB-A succeeds, JOB-B fails.
        failed = False
        try:
            job_monitor.monitor_jobs()
        except RuntimeError as error:
            failed = (
                str(error) == "Simulated transient persistence failure"
            )

        check("ROUND1_FAILURE_PROPAGATED", failed)
        check("ROUND1_CHECKPOINT_UNCHANGED",
              checkpoint == old_checkpoint)
        check("ROUND1_JOB_A_CREATED",
              ("E2E-RETRY-A", "JOB_TIMEOUT", "CREATED") in events)
        check("ROUND1_JOB_B_NOT_SAVED",
              ("E2E-RETRY-B", "JOB_FAILED") not in active_alerts)

        # Round 2: retry the same scan window.
        job_monitor.monitor_jobs()

        check("ROUND2_CHECKPOINT_ADVANCED",
              checkpoint == scan_upper_bound)
        check("ROUND2_JOB_A_DUPLICATE",
              ("E2E-RETRY-A", "JOB_TIMEOUT", "DUPLICATE") in events)
        check("ROUND2_JOB_B_CREATED",
              ("E2E-RETRY-B", "JOB_FAILED", "CREATED") in events)

        check("NO_DUPLICATE_ALERT_RECORDS",
              len(active_alerts) == 2)
        check("CHECKPOINT_UPDATED_ONCE",
              checkpoint_updates == [scan_upper_bound])

    print("[TEST] ALL PASS: JOB Monitor Retry & Idempotency")


if __name__ == "__main__":
    main()
