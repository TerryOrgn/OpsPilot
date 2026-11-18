"""Operations scoped to this acceptance session."""
import os
import uuid
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

def analyze_selected(execution_id):
    if execution_id not in owned:
        raise ValueError('Unknown execution')
    rows = query(
        "SELECT j.STATUS, a.ALERT_TYPE, TIMESTAMPDIFF(SECOND,j.START_TIME,COALESCE(j.END_TIME,NOW(3))) AS DURATION_SECONDS FROM JOB_EXECUTION_LOG j JOIN JOB_ALERT_HISTORY a "
        "ON a.EXECUTION_ID=j.EXECUTION_ID WHERE j.EXECUTION_ID=%s "
        "AND a.ALERT_STATUS='OPEN' AND ((a.ALERT_TYPE='JOB_FAILED' AND j.STATUS='FAILED') OR (a.ALERT_TYPE='JOB_TIMEOUT' AND j.STATUS IN ('RUNNING','SUCCESS'))) LIMIT 1",
        (execution_id,), True,
    )
    if not rows:
        return {"message": "所选 JOB 没有待分析的失败或超时告警。"}
    from job_ai_analysis import analyze_job_abnormalities
    model = os.getenv("OPSPILOT_JOB_AI_MODEL")
    client = None
    if model and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
        except (ImportError, ValueError):
            pass
    result = analyze_job_abnormalities(
        dict(schema_version="1.1", tool_name="get_recent_abnormal_jobs",
             jobs=[{"status": rows[0]["STATUS"], "alert_type": rows[0]["ALERT_TYPE"], "duration_seconds": rows[0].get("DURATION_SECONDS")}], total_abnormal_count=1,
             returned_count=1, abnormal_count=1, truncated=False),
        client=client, model=model,
    )
    message = ("已知事实：所选 JOB 存在超时告警，告警未关闭。"
               if rows[0]["ALERT_TYPE"] == "JOB_TIMEOUT"
               else "已知事实：所选 JOB 执行失败，告警未关闭。")
    if result["status"] == "ok":
        message += " 可能原因：" + "；".join(result["possible_causes"])
        message += " 排查建议：" + "；".join(result["next_steps"])
    else:
        message += " AI 分析暂不可用。"
    return {"message": message}


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
        job_monitor.monitor_jobs(checkpoint_name=checkpoint, execution_id=execution_id)
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
