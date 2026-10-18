import logging


from datetime import datetime
from db import (
    get_checkpoint,
    get_incremental_jobs,
    update_checkpoint, get_running_jobs, get_job_by_execution_id
)
from alert_manager import save_alert,resolve_alert

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 1800

def auto_resolve_job_alerts(job):
    """
    根据JOB当前状态自动恢复不再适用的告警。
    """

    execution_id = job["EXECUTION_ID"]
    job_name = job["JOB_NAME"]
    status = job["STATUS"]

    # JOB最终执行失败：
    # 运行阶段结束，关闭运行超时告警。
    # 失败告警仍需保留。
    if status == "FAILED":

        resolved = resolve_alert(
            execution_id,
            "JOB_TIMEOUT",
            "JOB已结束且执行失败，运行超时告警由失败事件接管"
        )

        if resolved:
            logger.info(
                "[RESOLVED] %s JOB_TIMEOUT",
                job_name
            )

    # JOB执行成功
    elif status == "SUCCESS":

        end_time = job["END_TIME"]
        start_time = job["START_TIME"]

        if end_time is None:
            return

        if end_time < start_time:
            return

        duration = (
            end_time - start_time
        ).total_seconds()

        # 仅当最终耗时符合要求时，
        # 才允许自动关闭JOB_TIMEOUT。
        if 0 <= duration <= MAX_DURATION_SECONDS:

            resolved = resolve_alert(
                execution_id,
                "JOB_TIMEOUT",
                "JOB执行成功，最终耗时符合阈值要求"
            )

            if resolved:
                logger.info(
                    "[RESOLVED] %s JOB_TIMEOUT",
                    job_name
                )



def detect_job_alert(job):
    """
    检测JOB异常。

    返回:
        None: 没有异常
        dict: 异常信息
    """

    job_name = job["JOB_NAME"]
    status = job["STATUS"]

    start_time = job["START_TIME"]
    end_time = job["END_TIME"]

    if start_time is None:
        return {
            "type": "INVALID_EXECUTION_DATA",
            "level": "WARNING",
            "message": f"{job_name}缺少开始时间"
        }

    if end_time is not None and end_time < start_time:
        return {
            "type": "INVALID_EXECUTION_DATA",
            "level": "WARNING",
            "message": f"{job_name}结束时间早于开始时间"
        }

    # 1. 执行失败
    if status == "FAILED":

        return {
            "type": "JOB_FAILED",
            "level": "CRITICAL",
            "message": (
                f"{job_name}执行失败: "
                f"{job['ERROR_MESSAGE']}"
            )
        }

    # 2. 正在运行
    if status == "RUNNING":

        duration = (
            datetime.now() - start_time
        ).total_seconds()

        if duration < 0:
            return {
                "type": "INVALID_EXECUTION_DATA",
                "level": "WARNING",
                "message": f"{job_name}开始时间晚于当前时间"
            }

        if duration > MAX_DURATION_SECONDS:

            return {
                "type": "JOB_TIMEOUT",
                "level": "WARNING",
                "message": (
                    f"{job_name}运行超时，"
                    f"已运行{duration:.0f}秒"
                )
            }

        return None

    # 3. 执行成功
    if status == "SUCCESS":

        if end_time is None:
            return {
                "type": "INVALID_EXECUTION_DATA",
                "level": "WARNING",
                "message": f"{job_name}缺少结束时间"
            }

        duration = (
            end_time - start_time
        ).total_seconds()

        if duration > MAX_DURATION_SECONDS:

            return {
                "type": "JOB_TIMEOUT",
                "level": "WARNING",
                "message": (
                    f"{job_name}执行耗时过长，"
                    f"耗时{duration:.0f}秒"
                )
            }

        return None

    # 4. 未知状态
    return {
        "type": "UNKNOWN_STATUS",
        "level": "WARNING",
        "message": f"{job_name}状态异常: {status}"
    }


def monitor_jobs():
    try:
        # 执行JOB监控
        print("\n========== OpsPilot Incremental JOB Monitor ==========")

        # 1. 读取Checkpoint
        checkpoint = get_checkpoint()

        last_scan_time = checkpoint["LAST_SCAN_TIME"]

        print(f"[CHECKPOINT] 上次水位: {last_scan_time}")

        # 2. 查询增量JOB

        incremental_jobs, scan_upper_bound = get_incremental_jobs(
            last_scan_time,
            overlap_minutes=5
        )

        running_jobs = get_running_jobs()

        # 使用 EXECUTION_ID 合并去重
        # 先放入 RUNNING JOB
        job_map = {
            job["EXECUTION_ID"]: job
            for job in running_jobs
        }

        # 再放入增量 JOB
        for job in incremental_jobs:
            job_map[job["EXECUTION_ID"]] = job

        jobs = list(job_map.values())

        print(f"[SCAN] 增量JOB数量: {len(incremental_jobs)}")
        print(f"[SCAN] RUNNING JOB数量: {len(running_jobs)}")
        print(f"[SCAN] 合并去重后JOB数量: {len(jobs)}")

        # 3. 逐条处理JOB
        for job in jobs:

            latest_job = get_job_by_execution_id(
                job["EXECUTION_ID"]
            )

            if latest_job is None:
                raise RuntimeError(
                    f"JOB执行记录在扫描过程中消失: {job['EXECUTION_ID']}"
                )

            # 使用最新的数据库状态
            job = latest_job

            alert = detect_job_alert(job)

            if alert is not None:

                result = save_alert(
                    job,
                    alert["type"],
                    alert["level"],
                    alert["message"]
                )

                event_type = result["event_type"]

                if event_type == "CREATED":
                    print(
                        f"[NEW ALERT] "
                        f"EXECUTION_ID={job['EXECUTION_ID']} "
                        f"JOB_NAME={job['JOB_NAME']} "
                        f"ALERT_TYPE={alert['type']}"
                    )
                elif event_type == "REOPENED":

                    print(
                        f"[REOPENED] "
                        f"EXECUTION_ID={job['EXECUTION_ID']} "
                        f"JOB_NAME={job['JOB_NAME']} "
                        f"ALERT_TYPE={alert['type']}"
                    )

                elif event_type == "DUPLICATE":

                    print(
                        f"[DUPLICATE] "
                        f"EXECUTION_ID={job['EXECUTION_ID']} "
                        f"JOB_NAME={job['JOB_NAME']} "
                        f"ALERT_TYPE={alert['type']}"
                    )

                else:
                    raise ValueError(
                        f"未知告警事件类型: {event_type}"
                    )


            else:
                print(
                    f"[OK] {job['JOB_NAME']}: 无异常"
                )

            # 4. 自动恢复
            auto_resolve_job_alerts(job)

        # 5. 所有JOB处理成功后，推进Checkpoint
        update_checkpoint(scan_upper_bound)

        print(
            f"[CHECKPOINT] 水位已更新: {scan_upper_bound}"
        )

        print("[SUCCESS] 本轮监控完成")

    except Exception:
        logger.exception("OpsPilot JOB监控执行失败")
        raise



if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s - %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    monitor_jobs()