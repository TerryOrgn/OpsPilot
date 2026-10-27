
from audit_task_queue import BoundedAuditQueue


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


def make_audit(event_id):
    return {
        "event_id": event_id,
        "event": "JOB_MONITORING_SUMMARY",
        "tool_name": "get_recent_abnormal_jobs",
        "total_abnormal_count": 0,
        "returned_count": 0,
        "truncated": False,
        "summary_status": "SUCCESS",
    }


queue = BoundedAuditQueue(maxsize=2)

audit1 = make_audit("EVT-001")
audit2 = make_audit("EVT-002")
audit3 = make_audit("EVT-003")

# 1. 正常提交
result1 = queue.submit(audit1)
result2 = queue.submit(audit2)

check(
    "FIRST_QUEUED",
    result1["status"] == "QUEUED",
)

check(
    "SECOND_QUEUED",
    result2["status"] == "QUEUED",
)

check(
    "QUEUE_SIZE_TWO",
    queue.size() == 2,
)

# 2. 队列满时拒绝
result3 = queue.submit(audit3)

check(
    "FULL_QUEUE_REJECTED",
    result3["status"] == "REJECTED",
)

check(
    "FULL_REASON",
    result3["reason"] == "QUEUE_FULL",
)

check(
    "NO_OVER_CAPACITY",
    queue.size() == 2,
)

# 3. 提交时复制数据
audit1["event_id"] = "CHANGED"

item1 = queue.get_nowait()

check(
    "AUDIT_COPY_ISOLATED",
    item1["event_id"] == "EVT-001",
)

queue.task_done()

# 4. 出队后可以继续提交
result3 = queue.submit(audit3)

check(
    "SUBMIT_AFTER_DEQUEUE",
    result3["status"] == "QUEUED",
)

# 5. 关闭队列
queue.close()

result4 = queue.submit(make_audit("EVT-004"))

check(
    "CLOSED_QUEUE_REJECTED",
    result4["status"] == "REJECTED",
)

check(
    "CLOSED_REASON",
    result4["reason"] == "QUEUE_CLOSED",
)

check(
    "PENDING_ITEMS_PRESERVED",
    queue.size() == 2,
)

# 6. 已入队事件仍可读取
item2 = queue.get_nowait()
queue.task_done()

item3 = queue.get_nowait()
queue.task_done()

check(
    "FIFO_ORDER",
    [
        item2["event_id"],
        item3["event_id"],
    ] == ["EVT-002", "EVT-003"],
)

check(
    "QUEUE_EMPTY",
    queue.size() == 0,
)

check(
    "EMPTY_GET_RETURNS_NONE",
    queue.get_nowait() is None,
)

print("[TEST] ALL PASS: Bounded Audit Queue")
