
from db import get_connection
import logging

logger = logging.getLogger(__name__)

LOCK_NAME = "opspilot:job_monitor"


def run_with_monitor_lock(monitor_func):
    conn = get_connection()
    acquired = False
    business_error = None

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT GET_LOCK(%s, 0) AS acquired",
                (LOCK_NAME,)
            )
            result = cursor.fetchone()["acquired"]

        if result is None:
            raise RuntimeError("MySQL GET_LOCK failed")

        if result == 0:
            print("[LOCK] 监控任务正在其他实例执行，本轮跳过")
            return False

        if result != 1:
            raise RuntimeError(
                f"Unexpected GET_LOCK result: {result}"
            )

        acquired = True
        print("[LOCK] 获取监控锁成功")

        try:
            monitor_func()
        except Exception as exc:
            business_error = exc
            raise

        return True

    finally:
        try:
            if acquired:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT RELEASE_LOCK(%s) AS released",
                            (LOCK_NAME,)
                        )
                        released = cursor.fetchone()["released"]

                    if released != 1:
                        raise RuntimeError(
                            f"MySQL RELEASE_LOCK failed: {released}"
                        )

                    print("[LOCK] 监控锁已释放")

                except Exception:
                    logger.exception(
                        "Failed to release MySQL monitor lock"
                    )

                    # 如果业务本身已经失败，
                    # 不让释放锁异常覆盖原始业务异常
                    if business_error is None:
                        raise
        finally:
            conn.close()
