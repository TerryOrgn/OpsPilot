
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from notification_outbox_fallback_scheduler import (
    create_fallback_scheduler,
)


# 获取生产调度配置，但不启动 BlockingScheduler
production_scheduler = create_fallback_scheduler()
production_job = production_scheduler.get_job("fallback_worker")

assert production_job is not None

executed = threading.Event()


def mock_cycle():
    executed.set()


# 测试专用 BackgroundScheduler，不执行真实业务
scheduler = BackgroundScheduler()

scheduler.add_job(
    mock_cycle,
    trigger=production_job.trigger,
    id=production_job.id,
    max_instances=production_job.max_instances,
    coalesce=production_job.coalesce,
    misfire_grace_time=production_job.misfire_grace_time,
)

try:
    scheduler.start()

    assert scheduler.running
    print("[TEST] SCHEDULER_STARTED= True")

    # 立即触发测试任务，不等待 60 秒
    scheduler.modify_job(
        "fallback_worker",
        next_run_time=datetime.now(),
    )

    assert executed.wait(timeout=5), (
        "Scheduled job did not execute"
    )

    print("[TEST] SCHEDULED_JOB_EXECUTED= True")

finally:
    if scheduler.running:
        scheduler.shutdown(wait=True)

assert not scheduler.running
print("[TEST] SCHEDULER_STOPPED= True")

print("[TEST] ALL PASS: Fallback scheduler lifecycle")
