
from unittest.mock import MagicMock, patch

import monitor_lock


def make_connection(release_result=1):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value

    def execute(sql, params):
        if "GET_LOCK(" in sql:
            cursor.fetchone.return_value = {"acquired": 1}
        elif "RELEASE_LOCK(" in sql:
            cursor.fetchone.return_value = {
                "released": release_result
            }

    cursor.execute.side_effect = execute
    return conn


def failing_monitor():
    raise ValueError("Simulated business failure")


def main():
    # 场景 1：业务成功，释放失败
    conn = make_connection(release_result=0)

    with patch.object(monitor_lock, "get_connection", return_value=conn):
        try:
            monitor_lock.run_with_monitor_lock(lambda: None)
            raise AssertionError("预期释放锁异常")
        except RuntimeError as exc:
            assert "RELEASE_LOCK failed" in str(exc)

    conn.close.assert_called_once()
    print("[TEST] RELEASE_FAILURE_PROPAGATED=PASS")

    # 场景 2：业务失败，同时释放失败
    conn = make_connection(release_result=0)

    with patch.object(monitor_lock, "get_connection", return_value=conn):
        with patch.object(monitor_lock.logger, "exception") as log:
            try:
                monitor_lock.run_with_monitor_lock(failing_monitor)
                raise AssertionError("预期业务异常")
            except ValueError as exc:
                assert str(exc) == "Simulated business failure"

            log.assert_called_once()
            assert "release" in log.call_args.args[0].lower()

    conn.close.assert_called_once()
    print("[TEST] BUSINESS_ERROR_PRESERVED=PASS")
    print("[TEST] RELEASE_ERROR_LOGGED=PASS")

    print("[TEST] ALL PASS: JOB-E2E-8D")


if __name__ == "__main__":
    main()
