
import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from notification_scheduler import run_notification_cycle

scheduler = BlockingScheduler()
run_count = 0
stop_requested = threading.Event()


def test_cycle():
    global run_count

    run_count += 1

    print(f"\n[TEST-SCHEDULER] RUN={run_count}")

    result = run_notification_cycle(
        notification_type="CONSOLE_TEST_CYCLE",
        limit=1
    )

    print(f"[TEST-SCHEDULER] RESULT={result}")

    if result["dispatch"]["errors"] > 0:
        print("[TEST-SCHEDULER] WARNING: Dispatcher errors detected")

    if run_count >= 3:
        print("[TEST-SCHEDULER] Completed 3 runs")
        stop_requested.set()


def stop_watcher():
    stop_requested.wait()

    # 在独立线程中发起关闭，避免工作线程等待自身退出
    scheduler.shutdown(wait=True)


scheduler.add_job(
    test_cycle,
    trigger="interval",
    seconds=5,
    id="test_notification_cycle",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=3
)

print("[TEST-SCHEDULER] START interval=5s")

threading.Thread(
    target=stop_watcher,
    daemon=True
).start()

try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    print("[TEST-SCHEDULER] STOP")

print("[TEST-SCHEDULER] EXIT")
