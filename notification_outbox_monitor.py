
from notification_outbox import (
    get_exhausted_outbox_count,
    evaluate_outbox_exhausted_status,
)
from notification_outbox_monitor_state import (
    transition_outbox_monitor_state,
)
from notification_outbox_fallback import (
    emit_outbox_fallback_alert,
)


def run_outbox_monitor(notification_type="CONSOLE"):
    # 1. 查询最终失败事件数量
    exhausted_count = get_exhausted_outbox_count(
        notification_type
    )

    # 2. 计算当前监控状态
    new_status = evaluate_outbox_exhausted_status(
        exhausted_count
    )

    # 3. 持久化状态，识别是否发生转换
    transition = transition_outbox_monitor_state(
        notification_type,
        new_status
    )

    # 4. 只有状态变化时才输出兜底告警
    alert_emitted = False

    if transition["changed"]:
        alert_emitted = emit_outbox_fallback_alert(
            notification_type=notification_type,
            old_status=transition["old_status"],
            new_status=transition["new_status"],
            exhausted_count=exhausted_count
        )

    return {
        "notification_type": notification_type,
        "exhausted_count": exhausted_count,
        "status": new_status,
        "changed": transition["changed"],
        "alert_emitted": alert_emitted
    }


def execute_outbox_monitor(notification_type="CONSOLE"):
    import logging

    logger = logging.getLogger("opspilot.outbox.monitor")

    try:
        result = run_outbox_monitor(notification_type)

        logger.info(
            "[OUTBOX_MONITOR] "
            "notification_type=%s "
            "status=%s "
            "exhausted_count=%s "
            "changed=%s",
            notification_type,
            result["status"],
            result["exhausted_count"],
            result["changed"]
        )

        return {
            "success": True,
            "result": result,
            "error": None
        }

    except Exception as exc:
        logger.exception(
            "[OUTBOX_MONITOR_ERROR] "
            "notification_type=%s error=%s",
            notification_type,
            exc
        )

        return {
            "success": False,
            "result": None,
            "error": str(exc)
        }
