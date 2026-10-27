
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from notification_outbox_monitor import (
    execute_outbox_monitor,
)


logger = logging.getLogger("opspilot.outbox.scheduler")


def start_outbox_monitor_scheduler(
    notification_type="CONSOLE",
    interval_seconds=60
):
    if (
        not isinstance(interval_seconds, int)
        or isinstance(interval_seconds, bool)
        or interval_seconds <= 0
    ):
        raise ValueError(
            "interval_seconds must be a positive integer"
        )

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        execute_outbox_monitor,
        trigger="interval",
        seconds=interval_seconds,
        args=[notification_type],
        id=f"outbox_monitor_{notification_type}",
        max_instances=1,
        coalesce=True,
        replace_existing=True
    )

    scheduler.start()

    logger.info(
        "[OUTBOX_MONITOR_SCHEDULER] "
        "started notification_type=%s interval=%ss",
        notification_type,
        interval_seconds
    )

    return scheduler
