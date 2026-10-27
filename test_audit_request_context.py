
from contextvars import copy_context

from webhook_notification_recovery_trace_context import get_request_id, set_request_id, reset_request_id


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


# 保存当前上下文状态，避免影响后续测试
original_request_id = get_request_id()

token = set_request_id("REQ-BN3-001")

try:
    check(
        "REQUEST_ID_READABLE",
        get_request_id() == "REQ-BN3-001",
    )

    # 新上下文中覆盖 Request ID
    isolated_context = copy_context()

    def read_isolated_request():
        inner_token = set_request_id("REQ-BN3-002")
        try:
            return get_request_id()
        finally:
            reset_request_id(inner_token)

    isolated_id = isolated_context.run(
        read_isolated_request
    )

    check(
        "ISOLATED_CONTEXT_ID",
        isolated_id == "REQ-BN3-002",
    )

    check(
        "PARENT_CONTEXT_UNCHANGED",
        get_request_id() == "REQ-BN3-001",
    )

finally:
    reset_request_id(token)


check(
    "REQUEST_ID_RESTORED",
    get_request_id() == original_request_id,
)


print("[TEST] ALL PASS: Audit Request Context")
