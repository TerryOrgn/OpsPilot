
import logging
from urllib.error import HTTPError

from notification_outbox_fallback_dispatcher import (
    claim_pending_fallback_alerts,
    confirm_fallback_alert_sent,
    confirm_fallback_alert_failed,
    confirm_fallback_alert_conflict,
)

logger = logging.getLogger("opspilot.fallback.worker")


def run_fallback_worker(send_alert, limit=10):
    if not callable(send_alert):
        raise ValueError("send_alert must be callable")

    claimed = claim_pending_fallback_alerts(limit=limit)


    result = {
        "claimed": len(claimed),
        "sent": 0,
        "failed": 0,
        "conflicted": 0,
        "confirmation_errors": 0,
    }

    for alert in claimed:
        alert_id = alert["ALERT_ID"]
        claim_token = alert["CLAIM_TOKEN"]

        try:
            # send_alert 应在成功发送后正常返回；
            # 发送失败时抛出异常。
            send_alert(alert)

        except HTTPError as exc:
            try:
                if exc.code == 409:
                    confirmed = confirm_fallback_alert_conflict(
                        alert_id,
                        claim_token,
                    )

                    if confirmed:
                        result["conflicted"] += 1
                        print(
                            f"[FALLBACK_CONFLICT] "
                            f"alert_id={alert_id} status=EXHAUSTED"
                        )
                    else:
                        result["confirmation_errors"] += 1

                else:
                    confirmed = confirm_fallback_alert_failed(
                        alert_id,
                        claim_token,
                    )

                    if confirmed:
                        result["failed"] += 1
                    else:
                        result["confirmation_errors"] += 1

            except Exception:
                result["confirmation_errors"] += 1
                logger.exception(
                    "[FALLBACK_CONFIRM_ERROR] alert_id=%s",
                    alert_id,
                )

        except Exception:
            logger.exception(
                "[FALLBACK_SEND_ERROR] alert_id=%s",
                alert_id,
            )

            try:
                confirmed = confirm_fallback_alert_failed(
                    alert_id,
                    claim_token,
                )
                if confirmed:
                    result["failed"] += 1
                else:
                    result["confirmation_errors"] += 1
            except Exception:
                result["confirmation_errors"] += 1
                logger.exception(
                    "[FALLBACK_CONFIRM_ERROR] alert_id=%s",
                    alert_id,
                )

        else:
            try:
                confirmed = confirm_fallback_alert_sent(
                    alert_id,
                    claim_token,
                )
                if confirmed:
                    result["sent"] += 1
                else:
                    result["confirmation_errors"] += 1
            except Exception:
                result["confirmation_errors"] += 1
                logger.exception(
                    "[FALLBACK_CONFIRM_ERROR] alert_id=%s",
                    alert_id,
                )

    return result
