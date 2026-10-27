
from concurrent.futures import ThreadPoolExecutor

from db import get_connection
from webhook_alert_repository import WebhookAlertRepository


repo = WebhookAlertRepository()
alert_key = "TEST-92-48:WEBHOOK_ERROR_RATE"


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
    finally:
        connection.close()


def create_alert(_=None):
    return repo.create_or_update_alert(
        alert_key,
        "WEBHOOK_ERROR_RATE",
        "WARNING",
        "Webhook error rate exceeded threshold",
    )


try:
    cleanup()

    # 1. 并发首次创建
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(create_alert, range(5)))

    events = [r["event_type"] for r in results]

    assert events.count("CREATED") == 1, events
    assert events.count("DUPLICATE") == 4, events

    print("[TEST] CONCURRENT_FIRST_CREATE= True")

    # 2. 所有线程返回同一个告警 ID
    alert_ids = {r["alert_id"] for r in results}

    assert len(alert_ids) == 1

    print("[TEST] SAME_ALERT_ID= True")

    # 3. 检测次数正确
    alert = repo.get_alert(alert_key)

    assert alert["DETECT_COUNT"] == 5
    assert alert["ALERT_STATUS"] == "OPEN"

    print("[TEST] CONCURRENT_COUNT= True")

    # 4. 自动恢复
    assert repo.resolve_alert(
        alert_key,
        "Error rate normalized",
    ) is True

    print("[TEST] RESOLVED= True")

    # 5. 恢复后重新打开
    reopened = create_alert()

    assert reopened["event_type"] == "REOPENED"
    assert reopened["alert_status"] == "OPEN"
    assert reopened["detect_count"] == 6

    print("[TEST] REOPENED_EVENT= True")

    # 6. 再次检测
    duplicate = create_alert()

    assert duplicate["event_type"] == "DUPLICATE"
    assert duplicate["detect_count"] == 7

    print("[TEST] DUPLICATE_EVENT= True")

    # 7. 数据库中只有一条记录
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

    print("[TEST] SINGLE_RECORD= True")
    print("[TEST] ALL PASS: Webhook alert events")

finally:
    cleanup()
