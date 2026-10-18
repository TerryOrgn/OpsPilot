NOTIFIABLE_EVENTS = {"CREATED", "REOPENED"}


def should_notify(event_type: str) -> bool:
    """判断告警事件是否需要触发通知。"""
    return event_type in NOTIFIABLE_EVENTS


if __name__ == "__main__":

    test_events = [
        "CREATED",
        "DUPLICATE",
        "REOPENED",
        "RESOLVED",
    ]

    for event in test_events:
        print(
            f"event={event}, "
            f"should_notify={should_notify(event)}"
        )