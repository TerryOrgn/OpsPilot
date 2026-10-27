
import json
import os
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def send_fallback_webhook(alert):
    webhook_url = os.getenv("OPSPILOT_FALLBACK_WEBHOOK_URL")

    if not webhook_url:
        raise ValueError(
            "OPSPILOT_FALLBACK_WEBHOOK_URL is not configured"
        )

    parsed = urlsplit(webhook_url)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Invalid webhook URL")

    # 生产环境只允许 HTTPS。
    # HTTP 仅用于本机开发测试。
    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost", "127.0.0.1", "::1"
    ):
        raise ValueError("HTTP is allowed only for localhost")

    payload = {
        "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
        "alert_id": alert["ALERT_ID"],
        "notification_type": alert["NOTIFICATION_TYPE"],
        "old_status": alert["OLD_STATUS"],
        "new_status": alert["NEW_STATUS"],
    }

    body = json.dumps(payload).encode("utf-8")

    request = Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": str(alert["ALERT_ID"]),
        },
        method="POST",
    )

    # HTTP 非 2xx 会抛出 HTTPError；
    # 网络错误和超时也会抛出异常。
    # 由 Worker 捕获并记录失败。
    with urlopen(request, timeout=5) as response:
        status = response.status

        if not 200 <= status < 300:
            raise RuntimeError(
                f"Webhook returned HTTP {status}"
            )

    return True
