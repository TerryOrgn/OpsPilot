
from notification_recovery import recover_stale_notifications
from apscheduler.schedulers.blocking import BlockingScheduler
from notification_scheduler_stats import NotificationSchedulerStats
from notification_backlog import (
    get_notification_backlog,
    evaluate_backlog_status,
    get_exhausted_notification_count,
    evaluate_dead_letter_status,
)

from notification_exhaustion import (
    mark_exhausted_notifications,
    mark_stale_processing_exhausted
)

from notification_dispatcher import dispatch_claimed_notifications
from notification_monitor_state import transition_dead_letter_state


def run_notification_cycle(
    notification_type="CONSOLE",
    limit=10
):
    """
    单次通知处理周期：
    Recovery -> Exhaustion -> Dispatcher V2
    """

    print(
        f"[NOTIFICATION-CYCLE] START "
        f"TYPE={notification_type}"
    )

    # 1. 恢复超时通知
    recovered = recover_stale_notifications(
        notification_type=notification_type
    )

    # 2. 处理重试耗尽通知
    exhausted_failed = mark_exhausted_notifications(
        notification_type=notification_type
    )

    exhausted_stale = mark_stale_processing_exhausted(
        notification_type=notification_type
    )

    # 3. 领取并发送通知
    dispatch_stats = dispatch_claimed_notifications(
        limit=limit,
        notification_type=notification_type
    )

    result = {
        "recovered": recovered,
        "exhausted_failed": exhausted_failed,
        "exhausted_stale": exhausted_stale,
        "dispatch": dispatch_stats
    }

    print(f"[NOTIFICATION-CYCLE] END RESULT={result}")


    # 根据 Dispatcher 的处理结果判断本周期是否成功
    dispatcher_errors = dispatch_stats["errors"]
    dispatcher_failures = dispatch_stats["failed"]

    result["cycle_status"] = (
        "SUCCESS"
        if dispatcher_errors == 0 and dispatcher_failures == 0
        else "FAILED"
    )

    print(
        f"[NOTIFICATION-CYCLE] STATUS={result['cycle_status']} "
        f"DISPATCH_ERRORS={dispatcher_errors} "
        f"DISPATCH_FAILURES={dispatcher_failures}"
    )


    return result


# 当前进程内共享的通知调度统计
notification_stats = NotificationSchedulerStats()


def execute_notification_cycle(
    notification_type="CONSOLE",
    limit=10
):

    previous_health = notification_stats.get_health_status()

    """
    调度执行包装器：
    调用通知处理周期，并统一记录成功或失败。
    """

    try:
        result = run_notification_cycle(
            notification_type=notification_type,
            limit=limit
        )

        cycle_status = result["cycle_status"]

    except Exception as exc:
        cycle_status = "FAILED"
        result = {
            "cycle_status": "FAILED",
            "error": str(exc)
        }

        print(
            f"[NOTIFICATION-SCHEDULER] ERROR "
            f"TYPE={type(exc).__name__} "
            f"MESSAGE={exc}"
        )

    notification_stats.record_result(cycle_status)

    transition_event = notification_stats.detect_health_transition(
        previous_health
    )

    if transition_event is not None:
        print(
            f"[NOTIFICATION-HEALTH-EVENT] "
            f"EVENT={transition_event} "
            f"FROM={previous_health} "
            f"TO={notification_stats.get_health_status()}"
        )


    print(
        f"[NOTIFICATION-SCHEDULER] "
        f"STATUS={cycle_status} "
        f"STATS={notification_stats.snapshot()}"
    )


    # 记录本次执行结果后，重新评估调度器健康状态
    health_status = notification_stats.get_health_status()

    print(
        f"[NOTIFICATION-HEALTH] "
        f"STATUS={health_status} "
        f"CONSECUTIVE_FAILURES="
        f"{notification_stats.consecutive_failures}"
    )



    try:
        backlog = get_notification_backlog(notification_type)
        backlog_status = evaluate_backlog_status(backlog)

        try:
            exhausted_count = get_exhausted_notification_count(notification_type)
            result["exhausted_count"] = exhausted_count
            result["dead_letter_status"] = evaluate_dead_letter_status(
                exhausted_count
            )

            try:
                dead_letter_event = transition_dead_letter_state(
                    notification_type,
                    result["dead_letter_status"]
                )
                result["state_persistence_status"] = "SUCCESS"

            except Exception as exc:
                dead_letter_event = None
                result["state_persistence_status"] = "FAILED"

                print(
                    f"[NOTIFICATION-MONITOR-STATE] "
                    f"PERSIST_FAILED "
                    f"TYPE={notification_type} "
                    f"ERROR={type(exc).__name__} "
                    f"MESSAGE={exc}"
                )

            result["dead_letter_event"] = dead_letter_event

            if dead_letter_event:
                print(
                    f"[NOTIFICATION-DEAD-LETTER-EVENT] "
                    f"TYPE={notification_type} "
                    f"EVENT={dead_letter_event} "
                    f"EXHAUSTED={exhausted_count}"
                )

            print(
                f"[NOTIFICATION-DEAD-LETTER] "
                f"TYPE={notification_type} "
                f"EXHAUSTED={exhausted_count}"
            )
        except Exception as e:
            result["dead_letter_event"] = None
            result["exhausted_count"] = None
            result["dead_letter_status"] = "UNKNOWN"
            print(
                f"[NOTIFICATION-DEAD-LETTER] "
                f"CHECK_FAILED TYPE={type(e).__name__} "
                f"MESSAGE={e}"
            )

        print(
            f"[NOTIFICATION-BACKLOG] "
            f"TYPE={notification_type} "
            f"PENDING={backlog['pending']} "
            f"FAILED={backlog['failed']} "
            f"TOTAL={backlog['total']} "
            f"STATUS={backlog_status}"
        )


    except Exception as exc:
        backlog_status = "UNKNOWN"

        print(
            f"[NOTIFICATION-BACKLOG] "
            f"CHECK_FAILED "
            f"STATUS={backlog_status} "
            f"TYPE={type(exc).__name__} "
            f"MESSAGE={exc}"
        )



    result["backlog_status"] = backlog_status


    return result



def start_notification_scheduler():
    scheduler = BlockingScheduler()

    scheduler.add_job(
        execute_notification_cycle,
        trigger="interval",
        seconds=60,
        kwargs={
            "notification_type": "CONSOLE_TEST_CYCLE",
            "limit": 10
        },
        id="notification_dispatch_cycle",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
        replace_existing=True
    )

    print("[NOTIFICATION-SCHEDULER] START interval=60s")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[NOTIFICATION-SCHEDULER] STOP")


if __name__ == "__main__":
    start_notification_scheduler()