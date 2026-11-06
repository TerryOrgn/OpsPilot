"""Operations scoped to this acceptance session."""
import os
import uuid
from unittest.mock import patch
import db
import job_monitor
from job_runtime import RuntimeConfig, run_notification_batch
from notification_worker import claim_notification, complete_notification
from notification_recovery import recover_stale_notifications
owned = set()
checkpoint = 'UI_' + uuid.uuid4().hex[:20]

def query(sql, args=(), read=False):
    if any((os.environ.get(key) != 'opspilot_test' for key in ('MYSQL_DATABASE', 'OPSPILOT_EXPECTED_DATABASE'))):
        raise RuntimeError('The acceptance UI requires opspilot_test')
    c = db.get_connection()
    try:
        with c.cursor() as s:
            s.execute(sql, args)
            rows = s.fetchall() if read else None
        c.commit()
        return rows
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def action(name, execution_id=''):
    if name not in ('create', 'monitor', 'send', 'success', 'fail', 'crash', 'exhaust'):
        raise ValueError('Unknown action')
    if name == 'create':
        execution_id = 'UIJOB_' + uuid.uuid4().hex[:20]
        query("INSERT INTO JOB_EXECUTION_LOG (EXECUTION_ID,SYSTEM_ID,JOB_NAME,BUSINESS_DATE,START_TIME,END_TIME,STATUS,ERROR_MESSAGE) VALUES (%s,'UI_TEST',%s,CURRENT_DATE(),NOW(3),NOW(3),'FAILED','UI simulated failure')", (execution_id, '演示任务 ' + execution_id[-6:]))
        owned.add(execution_id)
        return {'message': '已创建并选中新任务，请运行监控。', 'execution_id': execution_id}
    if execution_id not in owned:
        raise ValueError('Select a JOB created in this UI session')
    if name in ('success', 'fail'):
        query('UPDATE JOB_EXECUTION_LOG SET STATUS=%s,END_TIME=NOW(3) WHERE EXECUTION_ID=%s', ('SUCCESS' if name == 'success' else 'FAILED', execution_id))
        return {'message': '状态已更新；点击运行监控'}
    if name == 'monitor':
        original = db.get_incremental_jobs

        def scoped(*args, **kwargs):
            rows, bound = original(*args, **kwargs)
            return ([r for r in rows if r['EXECUTION_ID'] == execution_id], bound)
        with patch.object(job_monitor, 'get_checkpoint', side_effect=lambda: db.get_checkpoint(checkpoint)), patch.object(job_monitor, 'update_checkpoint', side_effect=lambda bound: db.update_checkpoint(bound, checkpoint)), patch.object(job_monitor, 'get_incremental_jobs', side_effect=scoped), patch.object(job_monitor, 'get_running_jobs', return_value=[db.get_job_by_execution_id(execution_id)]):
            job_monitor.monitor_jobs()
        return {'message': '监控完成：已执行告警检测、去重与自动恢复'}
    rows = query("SELECT n.ID FROM JOB_NOTIFICATION_HISTORY n JOIN JOB_ALERT_HISTORY a ON a.ID=n.ALERT_ID WHERE a.EXECUTION_ID=%s AND n.NOTIFICATION_STATUS IN ('PENDING','FAILED','PROCESSING') ORDER BY n.ID", (execution_id,), True)
    if not rows:
        return {'message': '没有待处理通知（已发送或已耗尽）'}
    if name == 'send':
        sent = failed = waiting = skipped = 0
        config = RuntimeConfig.from_env()
        for row in rows:
            result = run_notification_batch(config, notification_id=row['ID'])
            sent += result['sent']
            failed += result['failed']
            if not (result['sent'] or result['failed'] or result['skipped']) and result['backlog'].get('FAILED'):
                waiting += 1
            elif not (result['sent'] or result['failed']):
                skipped += 1
        parts = []
        if sent:
            parts.append(f'已发送 {sent} 条通知')
        if failed:
            parts.append(f'发送失败 {failed} 条，请查看通知状态')
        if waiting:
            parts.append(f'{waiting} 条通知等待重试，间隔为 {config.retry_seconds} 秒')
        if skipped:
            parts.append(f'{skipped} 条通知当前不可发送')
        return {'message': '。'.join(parts) + '。'}

    recovered = exhausted = 0
    for row in rows:
        notification_id = row['ID']
        if name == 'crash':
            task = claim_notification(notification_id)
            if task:
                query(
                    'UPDATE JOB_NOTIFICATION_HISTORY SET PROCESSING_STARTED_AT='
                    'DATE_SUB(NOW(3), INTERVAL 600 SECOND) WHERE ID=%s',
                    (notification_id,),
                )
                recovered += recover_stale_notifications('CONSOLE', notification_id)
        else:
            for _ in range(3):
                task = claim_notification(notification_id)
                if not task:
                    break
                complete_notification(
                    notification_id, task['CLAIM_TOKEN'], False, 'UI simulated send failure'
                )
            updated = query(
                'SELECT NOTIFICATION_STATUS FROM JOB_NOTIFICATION_HISTORY WHERE ID=%s',
                (notification_id,), True,
            )
            exhausted += bool(updated and updated[0]['NOTIFICATION_STATUS'] == 'EXHAUSTED')
    if name == 'crash':
        return {'message': f'已回收 {recovered} 条超时通知。' if recovered else '没有可模拟回收的通知。'}
    return {'message': f'{exhausted} 条通知已达到失败上限，停止重试。' if exhausted else '没有通知达到失败上限。'}

def state():
    jobs = []
    alerts = []
    notifications = []
    for eid in sorted(owned):
        jobs.extend(query('SELECT EXECUTION_ID,JOB_NAME,STATUS,START_TIME,END_TIME FROM JOB_EXECUTION_LOG WHERE EXECUTION_ID=%s', (eid,), True))
        alerts.extend(query('SELECT ID,EXECUTION_ID,ALERT_TYPE,ALERT_STATUS,DETECT_COUNT FROM JOB_ALERT_HISTORY WHERE EXECUTION_ID=%s', (eid,), True))
        notifications.extend(query('SELECT n.ID,a.EXECUTION_ID,n.NOTIFICATION_STATUS,n.RETRY_COUNT,n.LAST_ERROR_MESSAGE FROM JOB_NOTIFICATION_HISTORY n JOIN JOB_ALERT_HISTORY a ON a.ID=n.ALERT_ID WHERE a.EXECUTION_ID=%s ORDER BY n.ID', (eid,), True))
    return dict(jobs=jobs, alerts=alerts, notifications=notifications, database='opspilot_test', checkpoint=checkpoint)

def initialize():
    query("INSERT INTO JOB_MONITOR_CHECKPOINT (MONITOR_NAME,LAST_SCAN_TIME,SCAN_STATUS) VALUES (%s,DATE_SUB(NOW(3),INTERVAL 1 DAY),'SUCCESS')", (checkpoint,))
