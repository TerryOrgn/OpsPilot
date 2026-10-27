
from db import get_connection


def get_notification_backlog(notification_type="CONSOLE_TEST_CYCLE"):
    """
    统计指定通知类型的待处理积压数量。
    """
    conn = get_connection()

    try:
        cursor = conn.cursor()

        try:
            sql = """
                SELECT
                    NOTIFICATION_STATUS,
                    COUNT(*) AS TOTAL
                FROM JOB_NOTIFICATION_HISTORY
                WHERE NOTIFICATION_TYPE = %s
                  AND NOTIFICATION_STATUS IN ('PENDING', 'FAILED')
                  AND RETRY_COUNT < 3
                GROUP BY NOTIFICATION_STATUS
            """

            cursor.execute(sql, (notification_type,))
            rows = cursor.fetchall()

            result = {
                "pending": 0,
                "failed": 0,
                "total": 0
            }

            for row in rows:
                # 兼容字典游标和普通元组游标
                if isinstance(row, dict):
                    status = row["NOTIFICATION_STATUS"]
                    count = row["TOTAL"]
                else:
                    status, count = row

                if status == "PENDING":
                    result["pending"] = count
                elif status == "FAILED":
                    result["failed"] = count

            result["total"] = (
                result["pending"] + result["failed"]
            )

            return result

        finally:
            cursor.close()

    finally:
        conn.close()



def evaluate_backlog_status(backlog, warning_threshold=10):
    """
    根据待处理通知数量判断积压状态。
    """
    if warning_threshold < 1:
        raise ValueError("warning_threshold must be >= 1")

    total = backlog["total"]

    if total >= warning_threshold:
        return "BACKLOG_WARNING"

    return "NORMAL"


def get_exhausted_notification_count(notification_type="CONSOLE_TEST_CYCLE"):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        try:
            sql = """
                SELECT COUNT(*)
                FROM JOB_NOTIFICATION_HISTORY
                WHERE NOTIFICATION_TYPE = %s
                  AND NOTIFICATION_STATUS = 'EXHAUSTED'
            """
            cursor.execute(sql, (notification_type,))
            row = cursor.fetchone()

            if isinstance(row, dict):
                return next(iter(row.values()))
            return row[0]
        finally:
            cursor.close()
    finally:
        conn.close()



def evaluate_dead_letter_status(exhausted_count):
    if exhausted_count is None:
        return "UNKNOWN"

    if exhausted_count < 0:
        raise ValueError("exhausted_count must be >= 0")

    if exhausted_count > 0:
        return "ACTION_REQUIRED"

    return "NORMAL"



def detect_dead_letter_transition(previous_status, current_status):
    if previous_status == "NORMAL" and current_status == "ACTION_REQUIRED":
        return "DEAD_LETTER_DETECTED"

    if previous_status == "ACTION_REQUIRED" and current_status == "NORMAL":
        return "DEAD_LETTER_CLEARED"

    return None



class DeadLetterStateTracker:
    def __init__(self):
        self.previous_status = None

    def update(self, current_status):
        if current_status == "UNKNOWN":
            return None

        if self.previous_status is None:
            self.previous_status = current_status
            return None

        event = detect_dead_letter_transition(
            self.previous_status,
            current_status
        )

        self.previous_status = current_status
        return event
