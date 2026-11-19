"""Validate collector events and atomically apply execution changes with receipts."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re

import pymysql


_AUTH_VALUE = re.compile(r"(?i)\b(authorization\s*[:=]\s*)(?:bearer\s+)?([^\s,;]+)")
_SECRET_VALUE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value, field, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"invalid_{field}")
    return value.strip()


def _event_time(value):
    raw = _text(value, "occurred_at", 64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_occurred_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("occurred_at_requires_timezone")
    utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    # The existing OpsPilot columns use DATETIME(3); normalize to millisecond precision.
    return utc.replace(microsecond=(utc.microsecond // 1000) * 1000)


def _error_message(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_error_message")
    text = " ".join(value.split())[:1000]
    text = _AUTH_VALUE.sub(r"\1[REDACTED]", text)
    return _SECRET_VALUE.sub(r"\1\2[REDACTED]", text) or None


def normalize_event(value, *, configured_system_id):
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported_event_schema")
    system_id = _text(value.get("system_id"), "system_id", 50)
    if system_id != configured_system_id:
        raise ValueError("system_id_mismatch")
    event_type = value.get("event_type")
    if event_type not in ("started", "finished"):
        raise ValueError("invalid_event_type")
    status = value.get("status")
    if event_type == "started" and status not in (None, "RUNNING"):
        raise ValueError("invalid_started_status")
    if event_type == "finished" and status not in ("SUCCESS", "FAILED"):
        raise ValueError("invalid_finished_status")
    business_date = _text(value.get("business_date"), "business_date", 10)
    if not _DATE.fullmatch(business_date):
        raise ValueError("invalid_business_date")
    try:
        parsed_business_date = date.fromisoformat(business_date)
    except ValueError as exc:
        raise ValueError("invalid_business_date") from exc

    event = {
        "schema_version": 1,
        "event_id": _text(value.get("event_id"), "event_id", 200),
        "system_id": system_id,
        "execution_id": _text(value.get("execution_id"), "execution_id", 64),
        "job_name": _text(value.get("job_name"), "job_name", 100),
        "business_date": parsed_business_date.isoformat(),
        "event_type": event_type,
        "occurred_at": _event_time(value.get("occurred_at")),
        "status": "RUNNING" if event_type == "started" else status,
        "error_message": _error_message(value.get("error_message")) if status == "FAILED" else None,
    }
    canonical = {**event, "occurred_at": event["occurred_at"].isoformat(timespec="milliseconds")}
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return event, digest


def _reject(connection, reason):
    connection.rollback()
    return {"status": "rejected", "reason": reason}


def apply_event(connection, event, digest):
    """Apply a single event and its receipt in the same MySQL transaction."""
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT PAYLOAD_SHA256 FROM JOB_COLLECTOR_EVENT_RECEIPT
                   WHERE SYSTEM_ID=%s AND EVENT_ID=%s FOR UPDATE""",
                (event["system_id"], event["event_id"]),
            )
            receipt = cursor.fetchone()
            if receipt:
                connection.rollback()
                if receipt["PAYLOAD_SHA256"] == digest:
                    return {"status": "duplicate"}
                return {"status": "rejected", "reason": "event_id_payload_conflict"}

            cursor.execute(
                """SELECT SYSTEM_ID, JOB_NAME, BUSINESS_DATE, START_TIME, END_TIME,
                          STATUS, ERROR_MESSAGE
                   FROM JOB_EXECUTION_LOG WHERE EXECUTION_ID=%s FOR UPDATE""",
                (event["execution_id"],),
            )
            job = cursor.fetchone()
            if job and (
                job["SYSTEM_ID"] != event["system_id"]
                or job["JOB_NAME"] != event["job_name"]
                or job["BUSINESS_DATE"].isoformat() != event["business_date"]
            ):
                return _reject(connection, "execution_metadata_conflict")

            if event["event_type"] == "started":
                if job is None:
                    cursor.execute(
                        """INSERT INTO JOB_EXECUTION_LOG
                           (EXECUTION_ID,SYSTEM_ID,JOB_NAME,BUSINESS_DATE,START_TIME,END_TIME,STATUS,ERROR_MESSAGE)
                           VALUES (%s,%s,%s,%s,%s,NULL,'RUNNING',NULL)""",
                        (event["execution_id"], event["system_id"], event["job_name"],
                         event["business_date"], event["occurred_at"]),
                    )
                elif not (
                    job["STATUS"] == "RUNNING"
                    and job["START_TIME"] == event["occurred_at"]
                    and job["END_TIME"] is None
                ):
                    return _reject(connection, "started_event_conflicts_with_execution_state")
            else:
                if job is None:
                    return _reject(connection, "started_event_required")
                if event["occurred_at"] < job["START_TIME"]:
                    return _reject(connection, "finished_before_started")
                if job["STATUS"] == "RUNNING":
                    cursor.execute(
                        """UPDATE JOB_EXECUTION_LOG
                           SET STATUS=%s, END_TIME=%s, ERROR_MESSAGE=%s
                           WHERE EXECUTION_ID=%s AND SYSTEM_ID=%s""",
                        (event["status"], event["occurred_at"], event["error_message"],
                         event["execution_id"], event["system_id"]),
                    )
                elif not (
                    job["STATUS"] == event["status"]
                    and job["END_TIME"] == event["occurred_at"]
                    and (job["ERROR_MESSAGE"] or None) == event["error_message"]
                ):
                    return _reject(connection, "terminal_event_conflict")

            cursor.execute(
                """INSERT INTO JOB_COLLECTOR_EVENT_RECEIPT
                   (SYSTEM_ID,EVENT_ID,EXECUTION_ID,EVENT_TYPE,PAYLOAD_SHA256)
                   VALUES (%s,%s,%s,%s,%s)""",
                (event["system_id"], event["event_id"], event["execution_id"],
                 event["event_type"], digest),
            )
        connection.commit()
        return {"status": "accepted"}
    except pymysql.err.IntegrityError as exc:
        connection.rollback()
        if exc.args and exc.args[0] == 1062:
            # A concurrent identical delivery may win the unique-key insert race.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT PAYLOAD_SHA256 FROM JOB_COLLECTOR_EVENT_RECEIPT WHERE SYSTEM_ID=%s AND EVENT_ID=%s",
                    (event["system_id"], event["event_id"]),
                )
                receipt = cursor.fetchone()
            if receipt and receipt["PAYLOAD_SHA256"] == digest:
                return {"status": "duplicate"}
            return {"status": "rejected", "reason": "execution_or_event_id_conflict"}
        raise
    except Exception:
        connection.rollback()
        raise
