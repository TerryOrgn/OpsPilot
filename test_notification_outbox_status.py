
from notification_outbox import evaluate_outbox_exhausted_status


# 1. 没有最终失败事件
assert evaluate_outbox_exhausted_status(0) == "NORMAL"
print("[TEST] ZERO_COUNT_NORMAL= True")


# 2. 存在一条最终失败事件
assert evaluate_outbox_exhausted_status(1) == "ACTION_REQUIRED"
print("[TEST] ONE_COUNT_ACTION_REQUIRED= True")


# 3. 存在多条最终失败事件
assert evaluate_outbox_exhausted_status(100) == "ACTION_REQUIRED"
print("[TEST] MANY_COUNT_ACTION_REQUIRED= True")


# 4. 非法输入必须拒绝
invalid_values = [-1, 1.5, "1", None, True, False]

for value in invalid_values:
    try:
        evaluate_outbox_exhausted_status(value)
    except ValueError:
        pass
    else:
        raise AssertionError(
            f"Expected ValueError for {value!r}"
        )

print("[TEST] INVALID_INPUT_REJECTED= True")
print("[TEST] ALL PASS: Outbox status evaluation")
