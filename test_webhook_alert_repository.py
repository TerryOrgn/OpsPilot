
from concurrent.futures import ThreadPoolExecutor

from webhook_alert_repository import WebhookAlertRepository
from db import get_connection


repo = WebhookAlertRepository()

alert_key = "TEST-92-46:WEBHOOK_ERROR_RATE"


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
        alert_key=alert_key,
        alert_type="WEBHOOK_ERROR_RATE",
        alert_level="WARNING",
        alert_message="Webhook error rate reached 30%",
    )

    assert first["alert_status"] == "OPEN"
    assert first["detect_count"] == 1

    print("[TEST] FIRST_CREATE= True")

    # 2. 重复检测
    second = repo.create_or_update_alert(
        alert_key=alert_key,
        alert_type="WEBHOOK_ERROR_RATE",
        alert_level="WARNING",
        alert_message="Webhook error rate remains high",
    )

    assert second["alert_id"] == first["alert_id"]
    assert second["detect_count"] == 2

    print("[TEST] DUPLICATE_UPDATE= True")

    # 3. 查询告警
    alert = repo.get_alert(alert_key)

    assert alert is not None
    assert alert["ALERT_STATUS"] == "OPEN"
    assert alert["DETECT_COUNT"] == 2

    print("[TEST] GET_ALERT= True")

    # 4. 并发重复检测
    def worker(_):
        return repo.create_or_update_alert(
            alert_key=alert_key,
            alert_type="WEBHOOK_ERROR_RATE",
            alert_level="WARNING",
            alert_message="Concurrent error rate alert",
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(worker, range(5)))

    assert all(
        item["alert_id"] == first["alert_id"]
        for item in results
    )

    print("[TEST] CONCURRENT_SAME_ALERT_ID= True")

    # 5. 检查累计检测次数
    final_alert = repo.get_alert(alert_key)

    assert final_alert["DETECT_COUNT"] == 7

    print("[TEST] CONCURRENT_DETECT_COUNT= True")

    # 6. 检查数据库中只有一条记录
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

            row = cursor.fetchone()

        assert row["TOTAL"] == 1

    finally:
        connection.close()

    print("[TEST] UNIQUE_ALERT_RECORD= True")
    print("[TEST] ALL PASS: Webhook alert repository")

finally:
    cleanup()
