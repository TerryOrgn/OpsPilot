"""JOB v1 runtime: bounded CONSOLE batches and validated configuration."""
import logging
import os
from dataclasses import dataclass
from db import get_connection
from notification_recovery import recover_stale_notifications
from notification_worker import send_console_notification

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RuntimeConfig:
    monitor_seconds: int = 60
    notification_seconds: int = 60
    batch: int = 10
    timeout: int = 300
    retry_seconds: int = 60
    log_level: str = 'INFO'

    @classmethod
    def from_env(cls):
        values = {}
        for field, env, default, maximum in (
            ('monitor_seconds','MONITOR_SECONDS',60,86400),
            ('notification_seconds','NOTIFICATION_SECONDS',60,86400),
            ('batch','NOTIFICATION_BATCH',10,1000),
            ('timeout','PROCESSING_TIMEOUT_SECONDS',300,86400),
            ('retry_seconds','RETRY_SECONDS',60,86400),
        ):
            value = int(os.getenv('OPSPILOT_'+env, str(default)))
            if not 1 <= value <= maximum:
                raise ValueError('Invalid OPSPILOT_'+env)
            values[field] = value
        level = os.getenv('OPSPILOT_LOG_LEVEL','INFO').upper()
        if level not in ('DEBUG','INFO','WARNING','ERROR','CRITICAL'):
            raise ValueError('Invalid OPSPILOT_LOG_LEVEL')
        return cls(**values, log_level=level)

def pending_ids(config, notification_id=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT ID FROM JOB_NOTIFICATION_HISTORY
                WHERE NOTIFICATION_TYPE='CONSOLE'
                  AND (%s IS NULL OR ID=%s)
                  AND (NOTIFICATION_STATUS='PENDING'
                       OR (NOTIFICATION_STATUS='FAILED' AND RETRY_COUNT < 3
                           AND UPDATED_AT <= DATE_SUB(NOW(3), INTERVAL %s SECOND)))
                ORDER BY CREATED_AT, ID LIMIT %s
            """, (notification_id, notification_id, config.retry_seconds, config.batch))
            return [row['ID'] for row in cursor.fetchall()]
    finally:
        connection.close()

def backlog(notification_id=None):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT NOTIFICATION_STATUS AS status, COUNT(*) AS count
                FROM JOB_NOTIFICATION_HISTORY WHERE NOTIFICATION_TYPE='CONSOLE'
                AND (%s IS NULL OR ID=%s) GROUP BY NOTIFICATION_STATUS""",
                (notification_id, notification_id))
            return {row['status']:row['count'] for row in cursor.fetchall()}
    finally:
        connection.close()

def run_notification_batch(config=None, notification_id=None):
    config = config or RuntimeConfig.from_env()
    result = {'recovered': recover_stale_notifications('CONSOLE', notification_id,
                                timeout_seconds=config.timeout), 'sent':0, 'failed':0, 'skipped':0}
    # Snapshot IDs first: a failed task can be attempted only once in this cycle.
    for task_id in pending_ids(config, notification_id):
        try:
            if send_console_notification(task_id, retry_seconds=config.retry_seconds):
                result['sent'] += 1
            else:
                result['skipped'] += 1
        except Exception as exc:
            result['failed'] += 1
            logger.error('notification_failed id=%s error_type=%s', task_id, type(exc).__name__)
    result['backlog'] = backlog(notification_id)
    logger.info('notification_batch %s', result)
    if result['failed']:
        logger.warning('notification_delivery_failures count=%s', result['failed'])
    return result


class SecretRedactingFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)
        for name, value in os.environ.items():
            if value and any(word in name.upper() for word in ('PASSWORD', 'SECRET', 'TOKEN', 'API_KEY')):
                text = text.replace(value, '<REDACTED>')
        return text


def configure_logging(level):
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.setLevel(level)
    for handler in root.handlers:
        handler.setFormatter(SecretRedactingFormatter(
            '%(asctime)s [%(levelname)s] %(name)s - %(message)s'))
