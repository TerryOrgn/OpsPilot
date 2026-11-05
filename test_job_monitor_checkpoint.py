
from datetime import datetime, timedelta
from unittest.mock import patch

import job_monitor
from alert_manager import resolve_alert, save_alert
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
            "EXECUTION_ID": "E2E-001",
            "JOB_NAME": "JobA",
            "STATUS": "RUNNING",
            "START_TIME": now - timedelta(minutes=40),
            "END_TIME": None,
            "ERROR_MESSAGE": None,
        },
        {
            "EXECUTION_ID": "E2E-002",
            "JOB_NAME": "JobB",
            "STATUS": "FAILED",
            "START_TIME": now - timedelta(minutes=10),
            "END_TIME": now,
            "ERROR_MESSAGE": "Database timeout",
        },
    ]

    checkpoint_updates = []
    saved_alerts = []
    fail_on_second_job = False

    def fake_get_checkpoint():
        return {"LAST_SCAN_TIME": old_checkpoint}

    def fake_get_incremental_jobs(last_scan_time, overlap_minutes):
        check("CHECKPOINT_READ_CORRECTLY", last_scan_time == old_checkpoint)
        return jobs, scan_upper_bound

    def fake_get_running_jobs():
        return [jobs[0]]

    def fake_get_job_by_execution_id(execution_id):
        return next(
            job for job in jobs
            if job["EXECUTION_ID"] == execution_id
        )

    def fake_save_alert(job, alert_type, level, message):
        if fail_on_second_job and job["EXECUTION_ID"] == "E2E-002":
            raise RuntimeError("Simulated alert persistence failure")

        saved_alerts.append((job["EXECUTION_ID"], alert_type))
        return {"event_type": "CREATED"}

    def fake_resolve_alert(execution_id, alert_type, reason):
        return False

    with patch.object(job_monitor, "get_checkpoint", fake_get_checkpoint), \
         patch.object(job_monitor, "get_incremental_jobs", fake_get_incremental_jobs), \
         patch.object(job_monitor, "get_running_jobs", fake_get_running_jobs), \
         patch.object(job_monitor, "get_job_by_execution_id", fake_get_job_by_execution_id), \
         patch.object(job_monitor, "save_alert", fake_save_alert), \
         patch.object(job_monitor, "resolve_alert", fake_resolve_alert), \
         patch.object(job_monitor, "update_checkpoint",
                      lambda value: checkpoint_updates.append(value)):

        # Scenario 1: all jobs processed successfully.
        job_monitor.monitor_jobs()

        check(
            "SUCCESS_CHECKPOINT_ADVANCED",
            checkpoint_updates == [scan_upper_bound],
        )
        check(
            "SUCCESS_TWO_ALERTS_SAVED",
            len(saved_alerts) == 2,
        )

        # Scenario 2: alert persistence fails on the second job.
        checkpoint_updates.clear()
        saved_alerts.clear()
        fail_on_second_job = True

        rejected = False
        try:
            job_monitor.monitor_jobs()
        except RuntimeError as error:
            rejected = (
                str(error) == "Simulated alert persistence failure"
            )

        check("FAILURE_PROPAGATED", rejected)
        check(
            "FAILURE_CHECKPOINT_NOT_ADVANCED",
            checkpoint_updates == [],
        )
        check(
            "FIRST_JOB_PROCESSED_BEFORE_FAILURE",
            saved_alerts == [("E2E-001", "JOB_TIMEOUT")],
        )

    print("[TEST] ALL PASS: JOB Monitor Checkpoint")


if __name__ == "__main__":
    main()
