
from webhook_alert_repository import WebhookAlertRepository
from db import get_connection


repo = WebhookAlertRepository()
alert_key = "TEST-92-47:WEBHOOK_ERROR_RATE"


def cleanup():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM WEBHOOK_METRICS_ALERT
                WHERE ALERT_KEY = %s
                """,
                (alert_key,),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


try:
    cleanup()

    # 1. 首次创建
    first = repo.create_or_update_alert(
        alert_key,
        "WEBHOOK_ERROR_RATE",
        "WARNING",
        "Error rate reached 30%",
    )

    assert first["event_type"] == "CREATED"
    assert first["alert_status"] == "OPEN"
    assert first["detect_count"] == 1

    print("[TEST] FIRST_CREATED= True")

    # 2. 持续异常
    duplicate = repo.create_or_update_alert(
        alert_key,
        "WEBHOOK_ERROR_RATE",
        "WARNING",
        "Error rate remains high",
    )

    assert duplicate["event_type"] == "UPDATED"
    assert duplicate["alert_id"] == first["alert_id"]
    assert duplicate["detect_count"] == 2

    print("[TEST] DUPLICATE_UPDATED= True")

    # 3. 自动恢复
    resolved = repo.resolve_alert(
        alert_key,
        "Error rate returned to normal",
    )

    assert resolved is True

    alert = repo.get_alert(alert_key)

    assert alert["ALERT_STATUS"] == "RESOLVED"
    assert alert["RESOLVED_AT"] is not None

    print("[TEST] AUTO_RESOLVED= True")

    # 4. 重复恢复
    resolved_again = repo.resolve_alert(
        alert_key,
        "Repeated recovery",
    )

    assert resolved_again is False

    print("[TEST] RESOLVE_IDEMPOTENT= True")

    # 5. 再次异常
    reopened = repo.create_or_update_alert(
        alert_key,
        "WEBHOOK_ERROR_RATE",
        "CRITICAL",
        "Error rate reached 40%",
    )

    assert reopened["event_type"] == "UPDATED"
    assert reopened["alert_id"] == first["alert_id"]
    assert reopened["alert_status"] == "OPEN"
    assert reopened["detect_count"] == 3

    print("[TEST] REOPENED= True")

    # 6. 重开后恢复字段清空
    alert = repo.get_alert(alert_key)

    assert alert["RESOLVED_AT"] is None
    assert alert["RESOLUTION_REASON"] is None
    assert alert["ALERT_LEVEL"] == "CRITICAL"

    print("[TEST] REOPEN_CLEARS_RESOLUTION= True")

    # 7. 最终只有一条记录
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS TOTAL
                FROM WEBHOOK_METRICS_ALERT
                WHERE ALERT_KEY = %s
                """,
                (alert_key,),
            )

            count = cursor.fetchone()["TOTAL"]

    finally:
        connection.close()

    assert count == 1

    print("[TEST] SINGLE_ALERT_RECORD= True")
    print("[TEST] ALL PASS: Webhook alert lifecycle")

finally:
    cleanup()
