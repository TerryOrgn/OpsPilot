
class WebhookAlertNotificationPolicy:

    def decide(
        self,
        db_event,
        retry_event="NO_CHANGE",
    ):
        # 数据库恢复后，同次运行补写异常并完成恢复

        VALID_DB_EVENTS = {
            "CREATED",
            "DUPLICATE",
            "REOPENED",
            "RESOLVED",
            "NO_CHANGE",
        }

        VALID_RETRY_EVENTS = {
            "CREATED",
            "DUPLICATE",
            "REOPENED",
            "RESOLVED",
            "NO_CHANGE",
        }

        if (
                not isinstance(db_event, str)
                or db_event not in VALID_DB_EVENTS
        ):
            raise ValueError(
                f"Unsupported db_event: {db_event!r}"
            )

        if (
                not isinstance(retry_event, str)
                or retry_event not in VALID_RETRY_EVENTS
        ):
            raise ValueError(
                f"Unsupported retry_event: {retry_event!r}"
            )


        if (
            retry_event in ("CREATED", "REOPENED")
            and db_event == "RESOLVED"
        ):
            return {
                "action": "SUPPRESS",
                "reason": "RECOVERED_IN_SAME_RUN",
                "events": [retry_event, db_event],
            }

        # 新异常需要通知
        if db_event in ("CREATED", "REOPENED"):
            return {
                "action": "SEND",
                "reason": "NEW_ACTIVE_ALERT",
                "events": [db_event],
            }

        # 正常恢复需要通知
        if db_event == "RESOLVED":
            return {
                "action": "SEND",
                "reason": "ALERT_RESOLVED",
                "events": [db_event],
            }

        # 补偿成功，并且当前窗口没有新事件
        if (
                db_event == "NO_CHANGE"
                and retry_event in ("CREATED", "REOPENED")
        ):
            return {
                "action": "SEND",
                "reason": "PENDING_ALERT_RECOVERED",
                "events": [retry_event],
            }

        # 持续异常或无变化
        return {
            "action": "SKIP",
            "reason": "NO_NOTIFIABLE_CHANGE",
            "events": [],
        }
