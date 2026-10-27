
import logging

from notification_outbox_fallback import (
    emit_outbox_fallback_alert,
)


# 配置日志输出
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(message)s"
)


# 1. 首次发现 Outbox 最终失败
result = emit_outbox_fallback_alert(
    notification_type="CONSOLE",
    old_status="NORMAL",
    new_status="ACTION_REQUIRED",
    exhausted_count=3
)

assert result is True
print("[TEST] ALERT_EMITTED= True")


# 2. 状态未变化，不重复输出告警
result = emit_outbox_fallback_alert(
    notification_type="CONSOLE",
    old_status="ACTION_REQUIRED",
    new_status="ACTION_REQUIRED",
    exhausted_count=3
)

assert result is False
print("[TEST] DUPLICATE_SUPPRESSED= True")


# 3. 最终失败事件清零，输出恢复日志
result = emit_outbox_fallback_alert(
    notification_type="CONSOLE",
    old_status="ACTION_REQUIRED",
    new_status="NORMAL",
    exhausted_count=0
)

assert result is True
print("[TEST] RECOVERY_EMITTED= True")

print("[TEST] ALL PASS: Outbox fallback alert")
