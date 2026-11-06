"""Authenticated, one-shot Vercel JOB monitor invocation."""
import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler

from job_monitor import monitor_jobs
from job_preflight import check_readiness
from job_runtime import RuntimeConfig, configure_logging, run_notification_batch
from monitor_lock import run_with_monitor_lock


def run_cycle():
    config = RuntimeConfig.from_env()
    configure_logging(config.log_level)
    check_readiness(config)
    result = {"status": "skipped", "reason": "lock_busy"}

    def process():
        monitor_jobs()
        stats = run_notification_batch(config)
        result.clear()
        result.update(status="completed", notifications=stats)

    run_with_monitor_lock(process)
    return result


class handler(BaseHTTPRequestHandler):
    def reply(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        secret = os.getenv("CRON_SECRET", "")
        if not secret or not hmac.compare_digest(
            self.headers.get("Authorization", "").encode(),
            f"Bearer {secret}".encode(),
        ):
            return self.reply(401, {"status": "unauthorized"})

        if os.getenv("OPSPILOT_CRON_ENABLED") != "1":
            return self.reply(503, {"status": "disabled"})

        target = os.getenv("MYSQL_DATABASE")
        if os.getenv("VERCEL_ENV") == "production":
            if target == "opspilot_test" or os.getenv("OPSPILOT_MYSQL_TLS") != "1":
                return self.reply(503, {"status": "invalid_database_configuration"})
        elif target != "opspilot_test":
            return self.reply(503, {"status": "test_database_required"})

        try:
            result = run_cycle()
        except Exception as exc:
            logging.error("job_cron_failed error_type=%s", type(exc).__name__)
            return self.reply(500, {"status": "failed"})
        return self.reply(200, result)
