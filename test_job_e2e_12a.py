"""Isolated JOB failure -> monitor -> notification -> recovery acceptance."""
import os
os.environ['MYSQL_DATABASE'] = 'opspilot_test'
os.environ['OPSPILOT_EXPECTED_DATABASE'] = 'opspilot_test'
import uuid
from unittest.mock import patch
import db
import job_monitor
from job_runtime import run_notification_batch
from test_job_e2e_10c import cleanup

def main():
    execution_id = 'E2E12A_' + uuid.uuid4().hex[:16]
    monitor_name = execution_id
    def execute(sql, args=(), read=False):
        c=db.get_connection()
        try:
            with c.cursor() as s:
                s.execute('SELECT DATABASE() AS db')
                if s.fetchone()['db'] != 'opspilot_test': raise RuntimeError('Wrong DB')
                s.execute(sql,args)
                result=s.fetchall() if read else None
            c.commit()
            return result
        except Exception:
            c.rollback(); raise
        finally: c.close()
    before=execute("SELECT * FROM JOB_MONITOR_CHECKPOINT WHERE MONITOR_NAME='JOB_MONITOR'",read=True)
    original_incremental=db.get_incremental_jobs
    original_running=db.get_running_jobs
    def scoped_incremental(*args,**kwargs):
        rows,bound=original_incremental(*args,**kwargs)
        return [r for r in rows if r['EXECUTION_ID']==execution_id],bound
    try:
        execute("INSERT INTO JOB_MONITOR_CHECKPOINT (MONITOR_NAME,LAST_SCAN_TIME,SCAN_STATUS) VALUES (%s,DATE_SUB(NOW(3),INTERVAL 1 DAY),'SUCCESS')",(monitor_name,))
        execute("INSERT INTO JOB_EXECUTION_LOG (EXECUTION_ID,SYSTEM_ID,JOB_NAME,BUSINESS_DATE,START_TIME,END_TIME,STATUS,ERROR_MESSAGE) VALUES (%s,'E2E_TEST','E2E12A',CURRENT_DATE(),NOW(3),NOW(3),'FAILED','test failure')",(execution_id,))
        with patch.object(job_monitor,'get_checkpoint',side_effect=lambda:db.get_checkpoint(monitor_name)), patch.object(job_monitor,'update_checkpoint',side_effect=lambda bound:db.update_checkpoint(bound,monitor_name)), patch.object(job_monitor,'get_incremental_jobs',side_effect=scoped_incremental), patch.object(job_monitor,'get_running_jobs',side_effect=lambda:[r for r in original_running() if r['EXECUTION_ID']==execution_id]):
            job_monitor.monitor_jobs()
            def notifications():
                return execute('SELECT n.ID,n.NOTIFICATION_STATUS FROM JOB_NOTIFICATION_HISTORY n JOIN JOB_ALERT_HISTORY a ON a.ID=n.ALERT_ID WHERE a.EXECUTION_ID=%s ORDER BY n.ID',(execution_id,),True)
            first=notifications()
            assert len(first)==1 and first[0]['NOTIFICATION_STATUS']=='PENDING'
            assert run_notification_batch(notification_id=first[0]['ID'])['sent']==1
            job_monitor.monitor_jobs()
            assert len(notifications())==1
            execute("UPDATE JOB_EXECUTION_LOG SET STATUS='SUCCESS', END_TIME=NOW(3) WHERE EXECUTION_ID=%s",(execution_id,))
            job_monitor.monitor_jobs()
            rows=notifications()
            assert len(rows)==2
            assert run_notification_batch(notification_id=rows[1]['ID'])['sent']==1
            assert all(r['NOTIFICATION_STATUS']=='SENT' for r in notifications())
            alerts=execute('SELECT ALERT_STATUS FROM JOB_ALERT_HISTORY WHERE EXECUTION_ID=%s',(execution_id,),True)
            assert alerts[0]['ALERT_STATUS']=='RESOLVED'
        assert execute("SELECT * FROM JOB_MONITOR_CHECKPOINT WHERE MONITOR_NAME='JOB_MONITOR'",read=True)==before
        print('[TEST] ALL PASS: JOB-E2E-12A (scoped scan; real DB monitor/alerts/worker)')
    finally:
        cleanup(execution_id)
        execute('DELETE FROM JOB_MONITOR_CHECKPOINT WHERE MONITOR_NAME=%s',(monitor_name,))
if __name__=='__main__': main()
