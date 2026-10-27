
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
import os
from urllib.parse import urlsplit

from notification_outbox_fallback_dispatcher import (
    recover_stale_fallback_alerts,
    requeue_due_failed_fallback_alerts,
)
from notification_outbox_fallback_worker import (
    run_fallback_worker,
)
from notification_outbox_fallback_webhook import (
    send_fallback_webhook,
)


logger = logging.getLogger("opspilot.fallback.scheduler")

INTERVAL_SECONDS = 60


def run_fallback_cycle():
    """
    执行一次 Fallback 告警处理周期。
    """

    logger.info("[FALLBACK_CYCLE_START]")

    try:
        recovered = recover_stale_fallback_alerts()
        requeued = requeue_due_failed_fallback_alerts()

        result = run_fallback_worker(
            send_alert=send_fallback_webhook,
            limit=10,
        )

        logger.info(
            "[FALLBACK_CYCLE_END] "
            "recovered=%s requeued=%s result=%s",
            recovered,
            requeued,
            result,
        )

        return result

    except Exception:
        logger.exception("[FALLBACK_CYCLE_ERROR]")
        raise


def create_fallback_scheduler():
    """
    创建调度器，但不立即启动。
    """

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_fallback_cycle,
        trigger="interval",
        seconds=INTERVAL_SECONDS,
        id="fallback_worker",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    return scheduler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


    webhook_url = os.getenv("OPSPILOT_FALLBACK_WEBHOOK_URL")

    if not webhook_url:
        raise SystemExit(
            "Missing OPSPILOT_FALLBACK_WEBHOOK_URL"
        )

    parsed = urlsplit(webhook_url)

    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
    ):
        raise SystemExit("Invalid webhook URL")

    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise SystemExit(
            "HTTP webhook is allowed only for localhost"
        )


    logger.info("[FALLBACK_SCHEDULER_START]")

    scheduler = create_fallback_scheduler()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[FALLBACK_SCHEDULER_STOP]")
