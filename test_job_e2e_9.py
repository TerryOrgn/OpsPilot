
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from monitor_lock import run_with_monitor_lock

# 必须在导入业务模块之前设置测试数据库
os.environ["MYSQL_DATABASE"] = "opspilot_test"

import scheduler as scheduler_module

from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
)


def reset_status():
    status = scheduler_module.monitor_status

    status.update({
        "last_run_time": None,
        "last_success_time": None,
        "last_error_time": None,
        "last_error_message": None,
        "total_runs": 0,
        "success_count": 0,
        "failure_count": 0,
        "consecutive_failures": 0,
    })


def make_event(code, retval=None, exception=None):
    return SimpleNamespace(
        code=code,
        job_id="opspilot_job_monitor",
        retval=retval,
        exception=exception,
    )


def test_success():
    reset_status()

    # 模拟命名锁获取成功，业务函数执行
    def fake_lock(monitor_func):
        assert monitor_func is scheduler_module.monitor_jobs
        return True

    with patch.object(
        scheduler_module,
        "run_with_monitor_lock",
        side_effect=fake_lock,
    ):
        result = scheduler_module.scheduled_monitor()

    assert result is True

    scheduler_module.on_job_event(
        make_event(EVENT_JOB_EXECUTED, retval=result)
    )

    status = scheduler_module.monitor_status

    assert status["total_runs"] == 1
    assert status["success_count"] == 1
    assert status["failure_count"] == 0
    assert status["last_success_time"] is not None

    print("[TEST] SUCCESS_STATISTICS=PASS")


def test_lock_skipped():
    reset_status()

    with patch.object(
        scheduler_module,
        "run_with_monitor_lock",
        return_value=False,
    ):
        result = scheduler_module.scheduled_monitor()

    assert result is False

    scheduler_module.on_job_event(
        make_event(EVENT_JOB_EXECUTED, retval=result)
    )

    status = scheduler_module.monitor_status

    assert status["total_runs"] == 0
    assert status["success_count"] == 0
    assert status["failure_count"] == 0
    assert status["last_success_time"] is None
    assert status["last_run_time"] is not None

    print("[TEST] LOCK_SKIP_NOT_COUNTED=PASS")


def test_failure():
    reset_status()

    error = RuntimeError("Simulated monitor failure")

    with patch.object(
        scheduler_module,
        "run_with_monitor_lock",
        side_effect=error,
    ):
        try:
            scheduler_module.scheduled_monitor()
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as exc:
            assert exc is error

    scheduler_module.on_job_event(
        make_event(EVENT_JOB_ERROR, exception=error)
    )

    status = scheduler_module.monitor_status

    assert status["total_runs"] == 1
    assert status["success_count"] == 0
    assert status["failure_count"] == 1
    assert status["consecutive_failures"] == 1
    assert status["last_error_time"] is not None
    assert status["last_error_message"] == str(error)

    print("[TEST] FAILURE_STATISTICS=PASS")


def test_skip_preserves_failure_streak():
    reset_status()

    status = scheduler_module.monitor_status
    status["consecutive_failures"] = 2

    scheduler_module.on_job_event(
        make_event(EVENT_JOB_EXECUTED, retval=False)
    )

    assert status["consecutive_failures"] == 2
    assert status["success_count"] == 0

    print("[TEST] SKIP_PRESERVES_FAILURE_STREAK=PASS")


if __name__ == "__main__":
    test_success()
    test_lock_skipped()
    test_failure()
    test_skip_preserves_failure_streak()

    print("[TEST] ALL PASS: JOB-E2E-9")
