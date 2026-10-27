
import logging


logger = logging.getLogger("opspilot.outbox.fallback")


def emit_outbox_fallback_alert(
    notification_type,
    old_status,
    new_status,
    exhausted_count
):
    if old_status == new_status:
        return False

    logger.warning(
        "[OUTBOX_FALLBACK_ALERT] "
        "notification_type=%s "
        "old_status=%s "
        "new_status=%s "
        "exhausted_count=%s",
        notification_type,
        old_status,
        new_status,
        exhausted_count
    )

    return True
