import logging
import time
import signal
from job_runtime import RuntimeConfig, run_notification_batch, configure_logging
from datetime import datetime



from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
)

from job_monitor import monitor_jobs
from monitor_lock import run_with_monitor_lock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

monitor_status = {
    "last_run_time": None,
    "last_success_time": None,
    "last_error_time": None,
    "last_error_message": None,
    "total_runs": 0,
    "success_count": 0,
    "failure_count": 0,
    "consecutive_failures": 0
}

def on_job_event(event):

    if event.job_id == "opspilot_notifications":
        logger.info("notification_scheduler_event code=%s", event.code)
        return

    now = datetime.now()

    if event.code == EVENT_JOB_ERROR:

        monitor_status["last_run_time"] = now
        monitor_status["last_error_time"] = now
        monitor_status["last_error_message"] = str(event.exception)

        monitor_status["total_runs"] += 1
        monitor_status["failure_count"] += 1
        monitor_status["consecutive_failures"] += 1

        logger.error(
            "调度任务执行失败: job_id=%s, error=%s",
            event.job_id,
            event.exception
        )
        print_monitor_status()


    elif event.code == EVENT_JOB_EXECUTED:

        if event.retval is False:
            monitor_status["last_run_time"] = now

            logger.warning(
                "调度任务跳过（MySQL命名锁被占用）: job_id=%s",
                event.job_id
            )
            print_monitor_status()
            return

        monitor_status["last_run_time"] = now
        monitor_status["last_success_time"] = now

        monitor_status["total_runs"] += 1
        monitor_status["success_count"] += 1
        monitor_status["consecutive_failures"] = 0

        logger.info(
            "调度任务执行成功: job_id=%s",
            event.job_id
        )
        print_monitor_status()

    elif event.code == EVENT_JOB_MAX_INSTANCES:

        logger.warning(
            "上一轮监控尚未结束，本轮跳过: job_id=%s",
            event.job_id
        )

    elif event.code == EVENT_JOB_MISSED:

        logger.warning(
            "调度任务错过计划执行时间: job_id=%s",
            event.job_id
        )

def build_scheduler(config=None):
    config = config or RuntimeConfig.from_env()
    service = BlockingScheduler()
    for func, seconds, job_id in (
        (scheduled_monitor, config.monitor_seconds, "opspilot_job_monitor"),
        (run_notification_batch, config.notification_seconds, "opspilot_notifications"),
    ):
        service.add_job(func, trigger="interval", seconds=seconds, id=job_id,
                        max_instances=1, coalesce=True, misfire_grace_time=30,
                        replace_existing=True)
    service.add_listener(on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
                         | EVENT_JOB_MAX_INSTANCES | EVENT_JOB_MISSED)
    return service


def main():
    config = RuntimeConfig.from_env()
    configure_logging(config.log_level)
    service = build_scheduler(config)
    def stop(signum, frame):
        if service.running:
            service.shutdown(wait=True)
    previous = signal.signal(signal.SIGTERM, stop)
    logger.info("JOB service starting monitor_seconds=%s notification_seconds=%s batch=%s",
                config.monitor_seconds, config.notification_seconds, config.batch)
    try:
        service.start()
    except (KeyboardInterrupt, SystemExit):
        if service.running:
            service.shutdown(wait=True)
    finally:
        signal.signal(signal.SIGTERM, previous)
        logger.info("JOB service stopped")


def test_long_running_monitor():

    logger.info("[TEST] 模拟监控任务开始")

    time.sleep(10)

    logger.info("[TEST] 模拟监控任务结束")

test_execution_count = 0


def test_monitor_exception():
    global test_execution_count

    test_execution_count += 1

    logger.info(
        "[TEST] 第%s次执行开始",
        test_execution_count
    )

    if test_execution_count == 2:
        logger.warning("[TEST] 模拟数据库连接异常")
        raise ConnectionError("模拟MySQL数据库连接失败")

    logger.info(
        "[TEST] 第%s次执行成功",
        test_execution_count
    )

def print_monitor_status():

    logger.info("========== OpsPilot Scheduler Status ==========")

    for key, value in monitor_status.items():
        logger.info("%s: %s", key, value)

    logger.info("==============================================")

def scheduled_monitor():
    executed = run_with_monitor_lock(monitor_jobs)

    if not executed:
        logger.warning(
            "本轮监控因命名锁被占用而跳过"
        )

    return executed

if __name__ == "__main__":
    from job_preflight import check_readiness

    try:
        check_readiness()
    except Exception as exc:
        detail = str(exc) if type(exc) is RuntimeError else type(exc).__name__
        raise SystemExit(f"JOB preflight failed: {detail}") from None
    main()