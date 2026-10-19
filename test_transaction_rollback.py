from unittest.mock import patch

import alert_manager


TEST_EXECUTION_ID = "TEST-ROLLBACK-001"

job = {
    "EXECUTION_ID": TEST_EXECUTION_ID,
    "SYSTEM_ID": "TEST",
    "JOB_NAME": "TestRollbackJob",
}

# 保存原始数据库连接函数
original_get_connection = alert_manager.get_connection


class FaultInjectingCursor:
    def __init__(self, real_cursor):
        self.real_cursor = real_cursor

    def __enter__(self):
        self.real_cursor.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.real_cursor.__exit__(
            exc_type,
            exc_value,
            traceback
        )

    def execute(self, sql, params=None):
        # 模拟通知任务 INSERT 失败
        normalized_sql = " ".join(sql.upper().split())

        if "INSERT INTO JOB_NOTIFICATION_HISTORY" in normalized_sql:
            print("[TEST] 模拟通知任务写入失败")
            raise RuntimeError(
                "Simulated notification insert failure"
            )

        return self.real_cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.real_cursor, name)


class FaultInjectingConnection:
    def __init__(self, real_connection):
        self.real_connection = real_connection

    def cursor(self):
        return FaultInjectingCursor(self.real_connection.cursor())

    def __getattr__(self, name):
        return getattr(self.real_connection, name)


def get_fault_connection():
    return FaultInjectingConnection(original_get_connection())


print("[TEST] 开始事务回滚测试")

with patch.object(
    alert_manager,
    "get_connection",
    side_effect=get_fault_connection,
):
    try:
        alert_manager.save_alert(
            job=job,
            alert_type="JOB_TIMEOUT",
            alert_level="CRITICAL",
            alert_message="Transactional Outbox rollback test",
        )

        raise AssertionError(
            "测试失败：预期的通知写入异常没有发生"
        )

    except RuntimeError as exc:
        if str(exc) != "Simulated notification insert failure":
            raise

        print(f"[TEST] 捕获预期异常: {exc}")

print("[TEST] 故障注入执行结束，请检查数据库")