
from unittest.mock import patch

from notification_outbox_monitor import (
    execute_outbox_monitor,
)


# 1. 模拟监控成功
mock_result = {
    "notification_type": "CONSOLE",
    "exhausted_count": 0,
    "status": "NORMAL",
    "changed": False,
    "alert_emitted": False
}

with patch(
    "notification_outbox_monitor.run_outbox_monitor",
    return_value=mock_result
) as mocked_monitor:

    result = execute_outbox_monitor("CONSOLE")

    assert result["success"] is True
    assert result["result"] == mock_result
    assert result["error"] is None

    mocked_monitor.assert_called_once_with("CONSOLE")

print("[TEST] SUCCESS_RESULT= True")


# 2. 模拟数据库连接异常
with patch(
    "notification_outbox_monitor.run_outbox_monitor",
    side_effect=ConnectionError("MySQL unavailable")
):
    with patch(
            "logging.getLogger"
    ) as mocked_get_logger:

        result = execute_outbox_monitor("CONSOLE")

        assert result["success"] is False
        assert result["result"] is None
        assert result["error"] == "MySQL unavailable"

        # 验证异常被记录
        mocked_logger = mocked_get_logger.return_value
        mocked_logger.exception.assert_called_once()

print("[TEST] DATABASE_ERROR_ISOLATED= True")


# 3. 异常发生后，后续调用仍能成功
with patch(
    "notification_outbox_monitor.run_outbox_monitor",
    return_value=mock_result
):
    result = execute_outbox_monitor("CONSOLE")

    assert result["success"] is True

print("[TEST] RECOVERY_AFTER_ERROR= True")

print("[TEST] ALL PASS: Outbox monitor executor")
