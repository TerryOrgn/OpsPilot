
from webhook_alert_notification_policy import (
    WebhookAlertNotificationPolicy,
)


policy = WebhookAlertNotificationPolicy()


def check(
    name,
    db_event,
    retry_event,
    expected_action,
    expected_reason,
):
    result = policy.decide(
        db_event=db_event,
        retry_event=retry_event,
    )

    assert result["action"] == expected_action, result
    assert result["reason"] == expected_reason, result

    print(f"[TEST] {name}= True")


# 1. 首次异常
check(
    "NEW_ALERT_SEND",
    "CREATED",
    "NO_CHANGE",
    "SEND",
    "NEW_ACTIVE_ALERT",
)

# 2. 持续异常
check(
    "DUPLICATE_SKIP",
    "DUPLICATE",
    "NO_CHANGE",
    "SKIP",
    "NO_NOTIFIABLE_CHANGE",
)

# 3. 再次异常
check(
    "REOPENED_SEND",
    "REOPENED",
    "NO_CHANGE",
    "SEND",
    "NEW_ACTIVE_ALERT",
)

# 4. 正常恢复
check(
    "RESOLVED_SEND",
    "RESOLVED",
    "NO_CHANGE",
    "SEND",
    "ALERT_RESOLVED",
)

# 5. 补偿 CREATED 后同次恢复
check(
    "CREATED_RESOLVED_SUPPRESS",
    "RESOLVED",
    "CREATED",
    "SUPPRESS",
    "RECOVERED_IN_SAME_RUN",
)

# 6. 补偿 REOPENED 后同次恢复
check(
    "REOPENED_RESOLVED_SUPPRESS",
    "RESOLVED",
    "REOPENED",
    "SUPPRESS",
    "RECOVERED_IN_SAME_RUN",
)

# 7. 补偿成功，无新窗口
check(
    "PENDING_CREATED_SEND",
    "NO_CHANGE",
    "CREATED",
    "SEND",
    "PENDING_ALERT_RECOVERED",
)

# 8. 补偿后仍然异常
check(
    "PENDING_DUPLICATE_SKIP",
    "DUPLICATE",
    "CREATED",
    "SKIP",
    "NO_NOTIFIABLE_CHANGE",
)

# 9. 没有变化
check(
    "NO_CHANGE_SKIP",
    "NO_CHANGE",
    "NO_CHANGE",
    "SKIP",
    "NO_NOTIFIABLE_CHANGE",
)

print(
    "[TEST] ALL PASS: Webhook alert notification policy"
)
