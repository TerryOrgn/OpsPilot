
from threading import Event, Thread

from audit_task_queue import BoundedAuditQueue


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def make_audit(event_id):
    return {"event_id": event_id}


# 场景一：空队列立即完成
queue = BoundedAuditQueue(maxsize=2)

check(
    "EMPTY_QUEUE_COMPLETED",
    queue.wait_until_done(timeout=0.1) is True,
)


# 场景二：已提交但未处理，等待超时
queue.submit(make_audit("EVT-001"))

check(
    "PENDING_TASK_TIMEOUT",
    queue.wait_until_done(timeout=0.01) is False,
)


# 场景三：出队不等于完成
item = queue.get_nowait()

check(
    "DEQUEUED_NOT_COMPLETED",
    item["event_id"] == "EVT-001"
    and queue.wait_until_done(timeout=0) is False,
)

queue.task_done()

check(
    "TASK_DONE_COMPLETED",
    queue.wait_until_done(timeout=0.1) is True,
)


# 场景四：跨线程完成任务
queue = BoundedAuditQueue(maxsize=2)
queue.submit(make_audit("EVT-002"))

started = Event()
release = Event()
finished = Event()


def consume():
    item = queue.get_nowait()
    started.set()

    release.wait(timeout=2)

    queue.task_done()
    finished.set()


thread = Thread(target=consume)
thread.start()

check(
    "WORKER_STARTED",
    started.wait(timeout=2),
)

check(
    "WORKER_NOT_YET_COMPLETED",
    queue.wait_until_done(timeout=0.01) is False,
)

release.set()

check(
    "WAIT_UNTIL_DONE_SUCCESS",
    queue.wait_until_done(timeout=2) is True,
)

check(
    "WORKER_FINISHED",
    finished.wait(timeout=2),
)

thread.join(timeout=2)

check(
    "THREAD_EXITED",
    not thread.is_alive(),
)


# 场景五：非法参数
try:
    queue.wait_until_done(timeout=-1)
except ValueError:
    invalid_timeout_rejected = True
else:
    invalid_timeout_rejected = False

check(
    "INVALID_TIMEOUT_REJECTED",
    invalid_timeout_rejected,
)

print(
    "[TEST] ALL PASS: Audit Queue Completion"
)
