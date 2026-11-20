"""Authenticated v1 single-system event ingestion for the customer-side collector."""
import hmac
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from db import get_connection
from job_collector_ingest import apply_event, normalize_event

MAX_BODY_BYTES = 1024 * 1024
MAX_EVENTS = 100


def configuration_ready():
    environment = os.getenv("VERCEL_ENV")
    target = os.getenv("INGEST_MYSQL_DATABASE")
    expected = os.getenv("INGEST_OPSPILOT_EXPECTED_DATABASE")
    monitor_target = os.getenv("MYSQL_DATABASE")
    monitor_expected = os.getenv("OPSPILOT_EXPECTED_DATABASE")
    if (
        not target or target != expected or target != monitor_target
        or monitor_target != monitor_expected
        or not os.getenv("INGEST_MYSQL_HOST")
        or os.getenv("INGEST_OPSPILOT_MYSQL_TLS") != "1"
        or not os.getenv("OPSPILOT_INGEST_SYSTEM_ID")
    ):
        return False
    if environment == "production":
        return target != "opspilot_test"
    if environment == "preview":
        return target == "opspilot_test"
    return False


def ingest_events(events, *, system_id):
    accepted, duplicates, rejected = [], [], []
    connection = get_connection(env_prefix="INGEST_")
    try:
        for value in events:
            event_id = value.get("event_id") if isinstance(value, dict) else None
            try:
                event, digest = normalize_event(value, configured_system_id=system_id)
            except ValueError as exc:
                rejected.append({"event_id": event_id[:200] if isinstance(event_id, str) else None,
                                 "reason": str(exc)[:100]})
                continue
            result = apply_event(connection, event, digest)
            if result["status"] == "accepted":
                accepted.append(event["event_id"])
            elif result["status"] == "duplicate":
                duplicates.append(event["event_id"])
            else:
                rejected.append({"event_id": event["event_id"], "reason": result["reason"]})
    finally:
        connection.close()
    return {"accepted_event_ids": accepted, "duplicate_event_ids": duplicates, "rejected": rejected}


class handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/collector/v1/events":
            return self.reply(404, {"status": "not_found"})
        if os.getenv("OPSPILOT_INGEST_ENABLED") != "1":
            return self.reply(503, {"status": "disabled"})
        token = os.getenv("OPSPILOT_INGEST_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        if (
            len(token) < 32 or len(supplied) > 4096
            or not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        ):
            return self.reply(401, {"status": "unauthorized"})
        if not configuration_ready():
            return self.reply(503, {"status": "invalid_database_configuration"})
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.reply(415, {"status": "unsupported_media_type"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size <= 0:
            return self.reply(400, {"status": "invalid_content_length"})
        if size > MAX_BODY_BYTES:
            return self.reply(413, {"status": "payload_too_large"})
        try:
            payload = json.loads(self.rfile.read(size))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.reply(400, {"status": "invalid_json"})
        if (
            not isinstance(payload, dict) or payload.get("schema_version") != 1
            or not isinstance(payload.get("events"), list)
            or not 1 <= len(payload["events"]) <= MAX_EVENTS
        ):
            return self.reply(400, {"status": "invalid_event_batch"})

        try:
            result = ingest_events(payload["events"], system_id=os.environ["OPSPILOT_INGEST_SYSTEM_ID"])
        except Exception as exc:
            error_code = None
            network_errno = None
            connection_failure = None
            if type(exc).__module__.startswith("pymysql.") and exc.args:
                candidate_code = exc.args[0]
                if type(candidate_code) is int:
                    error_code = candidate_code
            if error_code == 2003 and len(exc.args) > 1 and isinstance(exc.args[1], str):
                detail = exc.args[1].lower()
                errno_match = re.search(r"\[errno\s+(-?\d+)\]", detail)
                if errno_match:
                    network_errno = int(errno_match.group(1))
                if "timed out" in detail:
                    connection_failure = "timeout"
                elif "refused" in detail:
                    connection_failure = "refused"
                elif any(marker in detail for marker in (
                    "name or service not known", "temporary failure in name resolution",
                    "getaddrinfo failed", "nodename nor servname",
                )):
                    connection_failure = "dns"
                elif "no route to host" in detail:
                    connection_failure = "no_route"
                else:
                    connection_failure = "other"
            logging.error(
                "job_ingest_failed error_type=%s error_module=%s error_code=%s "
                "network_errno=%s connection_failure=%s",
                type(exc).__name__, type(exc).__module__, error_code,
                network_errno, connection_failure,
            )
            return self.reply(503, {"status": "temporarily_unavailable"})

        # Event data is committed before monitoring. The Cron cycle shares its lock and
        # may report skipped when another invocation is active; the next Cron run recovers.
        result["monitoring"] = "deferred"
        if (
            os.getenv("VERCEL_ENV") in ("production", "preview")
            and os.getenv("OPSPILOT_INGEST_TRIGGER_MONITOR") == "1"
            and os.getenv("OPSPILOT_CRON_ENABLED") == "1"
            and (result["accepted_event_ids"] or result["duplicate_event_ids"])
        ):
            try:
                from api.job_cron import run_cycle
                cycle = run_cycle()
                result["monitoring"] = cycle.get("status", "deferred")
            except Exception as exc:
                logging.error("job_ingest_monitor_trigger_failed error_type=%s", type(exc).__name__)
                result["monitoring"] = "deferred"
        return self.reply(200, result)
