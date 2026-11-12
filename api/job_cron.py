"""Authenticated, one-shot Vercel JOB monitor invocation."""
import hmac
import json
import logging
import os
import re
from contextlib import closing
from http.server import BaseHTTPRequestHandler

from db import get_connection, get_job_by_execution_id
from job_monitor import monitor_jobs
from job_preflight import check_readiness
from job_runtime import RuntimeConfig, configure_logging, run_notification_batch
from monitor_lock import run_with_monitor_lock


def preview_execution_id():
    execution_id = os.getenv("OPSPILOT_PREVIEW_EXECUTION_ID", "")
    if (
        os.getenv("MYSQL_DATABASE") != "opspilot_test"
        or os.getenv("OPSPILOT_EXPECTED_DATABASE") != "opspilot_test"
        or os.getenv("OPSPILOT_MYSQL_TLS") != "1"
        or not re.fullmatch(r"PREVIEW_[0-9a-f]{20}", execution_id)
    ):
        raise ValueError("Invalid Preview database or fixture configuration")
    return execution_id


def preview_notification_ids(execution_id, config):
    with closing(get_connection()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT n.ID
            FROM JOB_NOTIFICATION_HISTORY n
            JOIN JOB_ALERT_HISTORY a ON a.ID = n.ALERT_ID
            WHERE a.EXECUTION_ID = %s AND n.NOTIFICATION_TYPE = 'CONSOLE'
              AND (n.NOTIFICATION_STATUS = 'PENDING'
                   OR (n.NOTIFICATION_STATUS = 'FAILED' AND n.RETRY_COUNT < 3
                       AND n.UPDATED_AT <= DATE_SUB(NOW(3), INTERVAL %s SECOND))
                   OR (n.NOTIFICATION_STATUS = 'PROCESSING'
                       AND n.PROCESSING_STARTED_AT < DATE_SUB(NOW(3), INTERVAL %s SECOND)))
            ORDER BY n.ID LIMIT %s
            """,
            (execution_id, config.retry_seconds, config.timeout, min(config.batch, 10)),
        )
        return [row["ID"] for row in cursor.fetchall()]


def run_cycle():
    config = RuntimeConfig.from_env()
    configure_logging(config.log_level)
    execution_id = preview_execution_id() if os.getenv("VERCEL_ENV") == "preview" else None
    if execution_id:
        check_readiness(config, checkpoint_name=execution_id)
    else:
        check_readiness(config)
    result = {"status": "skipped", "reason": "lock_busy"}

    def process():
        if execution_id:
            fixture = get_job_by_execution_id(execution_id)
            if not fixture or fixture["SYSTEM_ID"] != "PREVIEW_TEST":
                raise ValueError("Preview fixture is missing or has the wrong system ID")
            monitor_jobs(checkpoint_name=execution_id, execution_id=execution_id)
            stats = [
                {"id": notification_id, **run_notification_batch(config, notification_id=notification_id)}
                for notification_id in preview_notification_ids(execution_id, config)
            ]
        else:
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
        elif os.getenv("VERCEL_ENV") == "preview":
            try:
                preview_execution_id()
            except ValueError:
                return self.reply(503, {"status": "invalid_preview_configuration"})
        else:
            return self.reply(503, {"status": "unsupported_environment"})

        try:
            result = run_cycle()
        except Exception as exc:
            code = exc.args[0] if exc.args and type(exc.args[0]) is int else None
            cause = getattr(exc, "original_exception", None) or exc.__cause__ or exc.__context__
            logging.error(
                "job_cron_failed error_type=%s code=%s cause=%s",
                type(exc).__name__, code, type(cause).__name__ if cause else None,
            )
            result = {"status": "failed"}
            if os.getenv("VERCEL_ENV") == "preview":
                result["error_type"] = type(exc).__name__
                result["code"] = code
                result["cause"] = type(cause).__name__ if cause else None
            return self.reply(500, result)
        return self.reply(200, result)
