
import os
import runpy
from unittest.mock import patch


class SchedulerStarted(Exception):
    pass


def mock_start(self):
    raise SchedulerStarted()


with (
    patch.dict(
        os.environ,
        {
            "OPSPILOT_FALLBACK_WEBHOOK_URL":
                "http://127.0.0.1:9999/webhook"
        },
    ),
    patch(
        "apscheduler.schedulers.blocking."
        "BlockingScheduler.start",
        mock_start,
    ),
):
    try:
        runpy.run_module(
            "notification_outbox_fallback_scheduler",
            run_name="__main__",
        )
    except SchedulerStarted:
        print("[TEST] VALID_URL_ACCEPTED= True")
        print("[TEST] SCHEDULER_START_REACHED= True")
    else:
        raise AssertionError(
            "Expected scheduler start to be reached"
        )


print("[TEST] ALL PASS: Fallback scheduler startup")
