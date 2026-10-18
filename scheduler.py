import logging
import time
from datetime import datetime


from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
)

from job_monitor import monitor_jobs


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

def main():

    scheduler = BlockingScheduler()

    scheduler.add_job(
        func=monitor_jobs,
        trigger="interval",
        seconds=60,
        id="opspilot_job_monitor",
        name="OpsPilot JOB Monitor",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
        replace_existing=True
    )

    scheduler.add_listener(
        on_job_event,
        EVENT_JOB_EXECUTED
        | EVENT_JOB_ERROR
        | EVENT_JOB_MAX_INSTANCES
        | EVENT_JOB_MISSED
    )

    # logger.info("防重入测试启动")
    # logger.info("调度间隔: 5秒，模拟执行耗时: 10秒")
    logger.info("OpsPilot JOB监控服务启动")
    logger.info("监控间隔: 60秒")

    try:
        scheduler.start()

    except (KeyboardInterrupt, SystemExit):

        logger.info("OpsPilot调度服务停止")


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

if __name__ == "__main__":
    main()