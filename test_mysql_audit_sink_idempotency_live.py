
import json
import os
import uuid
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

from mysql_audit_sink import MySQLAuditSink


def create_connection():
    if os.environ.get("MYSQL_DATABASE") != "opspilot_test":
        raise RuntimeError("Audit integration requires MYSQL_DATABASE=opspilot_test")
    connection = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database="opspilot_test",
        connection_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            if cursor.fetchone() != ("opspilot_test",):
                raise RuntimeError("Audit integration connected to the wrong database")
    except Exception:
        connection.close()
        raise
    return connection


def check(name, condition):
    assert condition, name
    print(f"[LIVE] {name}=PASS")


def count_events(event_ids):
    connection = create_connection()
    try:
        cursor = connection.cursor()
        try:
            placeholders = ", ".join(["%s"] * len(event_ids))
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM AGENT_AUDIT_LOG
                WHERE EVENT_ID IN ({placeholders})
                """,
                tuple(event_ids),
            )
            return cursor.fetchone()[0]
        finally:
            cursor.close()
    finally:
        connection.close()


def cleanup(event_ids):
    connection = create_connection()
    try:
        cursor = connection.cursor()
        try:
            placeholders = ", ".join(["%s"] * len(event_ids))
            cursor.execute(
                f"""
                DELETE FROM AGENT_AUDIT_LOG
                WHERE EVENT_ID IN ({placeholders})
                """,
                tuple(event_ids),
            )
            deleted = cursor.rowcount
            connection.commit()
            print(f"[LIVE] CLEANUP_ROWS={deleted}")
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def main():
    if os.getenv("OPSPILOT_RUN_AUDIT_INTEGRATION") != "1":
        raise SystemExit("Set OPSPILOT_RUN_AUDIT_INTEGRATION=1 to enable this integration test")
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
    run_id = uuid.uuid4().hex[:16]
    event_a = f"EVT-BO5D-A-{run_id}"
    event_b = f"EVT-BO5D-B-{run_id}"
    request_id = f"REQ-BO5D-{run_id}"

    event_ids = [event_a, event_b]

    audit = {
        "event_id": event_a,
        "request_id": request_id,
        "event": "JOB_MONITORING_SUMMARY",
        "tool_name": "get_recent_abnormal_jobs",
        "total_abnormal_count": 0,
        "returned_count": 0,
        "truncated": False,
        "summary_status": "SUCCESS",
    }

    sink = MySQLAuditSink(
        connection_factory=create_connection
    )

    try:
        # 1. 第一次写入
        sink.write(json.dumps(audit))
        check(
            "FIRST_INSERT_COUNT",
            count_events(event_ids) == 1,
        )

        # 2. 同一个 EVENT_ID 重试
        sink.write(json.dumps(audit))
        check(
            "DUPLICATE_INSERT_COUNT",
            count_events(event_ids) == 1,
        )

        # 3. 不同 EVENT_ID 正常写入
        second_audit = {
            **audit,
            "event_id": event_b,
        }
        sink.write(json.dumps(second_audit))
        check(
            "NEW_EVENT_INSERT_COUNT",
            count_events(event_ids) == 2,
        )

    finally:
        # 无论测试断言是否通过，都尝试清理测试记录
        cleanup(event_ids)


    check(
        "CLEANUP_VERIFIED",
        count_events(event_ids) == 0,
    )

    print(f"[LIVE] REQUEST_ID={request_id}")
    print("[LIVE] ALL PASS: MySQL Audit Idempotency")


if __name__ == "__main__":
    main()
