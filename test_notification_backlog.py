
from unittest.mock import MagicMock, patch

from notification_backlog import get_notification_backlog


def main():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("PENDING", 5),
        ("FAILED", 3),
    ]

    with patch(
        "notification_backlog.get_connection",
        return_value=mock_conn
    ):
        result = get_notification_backlog(
            "CONSOLE_TEST_CYCLE"
        )

    assert result == {
        "pending": 5,
        "failed": 3,
        "total": 8
    }, f"Unexpected result: {result}"

    mock_cursor.execute.assert_called_once()

    # 验证 SQL 包含最大重试次数过滤条件
    sql, params = mock_cursor.execute.call_args.args

    normalized_sql = " ".join(sql.upper().split())

    assert "RETRY_COUNT < 3" in normalized_sql, (
        "SQL must exclude notifications with RETRY_COUNT >= 3"
    )

    assert params == ("CONSOLE_TEST_CYCLE",)

    print("[TEST] PASS: Retry limit filter")

    mock_cursor.close.assert_called_once()
    mock_conn.close.assert_called_once()

    print(f"[BACKLOG] {result}")
    print("[TEST] ALL PASS")


if __name__ == "__main__":
    main()
