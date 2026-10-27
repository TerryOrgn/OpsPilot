
from db import get_connection

from webhook_metrics import WebhookMetrics
from webhook_alert_repository import WebhookAlertRepository
from webhook_metrics_alert_service import (
    WebhookMetricsAlertService,
)


alert_key = "TEST-92-49:WEBHOOK_ERROR_RATE"

metrics = WebhookMetrics()
repo = WebhookAlertRepository()


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


def add_events(processed=0, errors=0):
    for _ in range(processed):
        metrics.record("PROCESSED")

    for _ in range(errors):
        metrics.record("ERROR")


def create_service():
    return WebhookMetricsAlertService(
        metrics=metrics,
        repository=repo,
        alert_key=alert_key,
        min_requests=10,
        error_threshold=20.0,
    )


try:
    cleanup()

    service = create_service()

    # 1. 首次采样
    result = service.run()

    assert result["monitor_status"] == "BASELINE"
    assert result["db_event"] == "NO_CHANGE"
    assert repo.get_alert(alert_key) is None

    print("[TEST] FIRST_BASELINE= True")

    # 2. 首次异常：30%
    add_events(processed=7, errors=3)

    result = service.run()

    assert result["pipeline_event"] == "NEW_ALERT"
    assert result["db_event"] == "CREATED"

    first_alert_id = result["alert_id"]

    print("[TEST] FIRST_ALERT_PERSISTED= True")

    # 3. 持续异常：20%
    add_events(processed=8, errors=2)

    result = service.run()

    assert result["pipeline_event"] == "DUPLICATE"
    assert result["db_event"] == "DUPLICATE"
    assert result["alert_id"] == first_alert_id

    print("[TEST] DUPLICATE_PERSISTED= True")

    # 4. 模拟监控组件重启
    service = create_service()

    # 重启后第一次运行只建立基线
    result = service.run()

    assert result["monitor_status"] == "BASELINE"
    assert result["db_event"] == "NO_CHANGE"

    print("[TEST] RESTART_BASELINE= True")

    # 5. 重启后仍然异常：30%
    add_events(processed=7, errors=3)

    result = service.run()

    assert result["pipeline_event"] == "NEW_ALERT"
    assert result["db_event"] == "DUPLICATE"
    assert result["alert_id"] == first_alert_id

    print("[TEST] RESTART_NO_DUPLICATE_ALERT= True")

    # 6. 恢复正常
    add_events(processed=10, errors=0)

    result = service.run()

    assert result["db_event"] == "RESOLVED"

    alert = repo.get_alert(alert_key)

    assert alert["ALERT_STATUS"] == "RESOLVED"

    print("[TEST] ALERT_AUTO_RESOLVED= True")

    # 7. 恢复后再次异常
    add_events(processed=6, errors=4)

    result = service.run()

    assert result["db_event"] == "REOPENED"
    assert result["alert_id"] == first_alert_id

    print("[TEST] ALERT_REOPENED= True")

    # 8. 最终状态验证
    alert = repo.get_alert(alert_key)

    assert alert["ALERT_STATUS"] == "OPEN"
    assert alert["DETECT_COUNT"] == 4

    print("[TEST] FINAL_DB_STATE= True")
    print("[TEST] ALL PASS: Webhook metrics alert service")

finally:
    cleanup()
