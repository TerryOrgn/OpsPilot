
from webhook_alert_notification_policy import (
    WebhookAlertNotificationPolicy,
)


policy = WebhookAlertNotificationPolicy()


def check_action(name, db_event, retry_event, expected):
    result = policy.decide(
        db_event=db_event,
        retry_event=retry_event,
    )

    assert result["action"] == expected, (
        f"{name}: expected={expected}, actual={result}"
    )

    print(f"[TEST] {name}= True")


def check_invalid(name, db_event, retry_event):
    try:
        policy.decide(
            db_event=db_event,
            retry_event=retry_event,
        )
    except ValueError:
        print(f"[TEST] {name}= True")
        return

    raise AssertionError(
        f"{name}: expected ValueError, "
        "but no exception was raised"
    )


# 1. 合法事件组合
check_action(
    "NORMAL_NO_CHANGE",
    "NO_CHANGE",
    "NO_CHANGE",
    "SKIP",
)

check_action(
    "CREATED_RESOLVED_SUPPRESS",
    "RESOLVED",
    "CREATED",
    "SUPPRESS",
)

check_action(
    "REOPENED_RESOLVED_SUPPRESS",
    "RESOLVED",
    "REOPENED",
    "SUPPRESS",
)

check_action(
    "PENDING_CREATED_SEND",
    "NO_CHANGE",
    "CREATED",
    "SEND",
)

check_action(
    "PENDING_DUPLICATE_SKIP",
    "DUPLICATE",
    "CREATED",
    "SKIP",
)


# 2. 未知数据库事件
check_invalid(
    "UNKNOWN_DB_EVENT",
    "CRETAED",
    "NO_CHANGE",
)


# 3. 未知补偿事件
check_invalid(
    "UNKNOWN_RETRY_EVENT",
    "NO_CHANGE",
    "REOPEND",
)


# 4. None 输入
check_invalid(
    "NONE_DB_EVENT",
    None,
    "NO_CHANGE",
)

check_invalid(
    "NONE_RETRY_EVENT",
    "NO_CHANGE",
    None,
)


# 5. 空字符串输入
check_invalid(
    "EMPTY_DB_EVENT",
    "",
    "NO_CHANGE",
)

check_invalid(
    "EMPTY_RETRY_EVENT",
    "NO_CHANGE",
    "",
)


print(
    "[TEST] ALL PASS: "
    "Webhook notification policy edge cases"
)
