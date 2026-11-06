import os, sys
os.environ['MYSQL_DATABASE']='opspilot_test'
from db import get_connection
from test_job_e2e_10c import create_test_notification, get_notification, cleanup
from notification_worker import claim_notification, complete_notification
from notification_recovery import recover_stale_notifications
def main():
    c=get_connection()
    with c.cursor() as s:
        s.execute('SELECT DATABASE() AS db')
        if s.fetchone()['db'] != 'opspilot_test': raise RuntimeError('Wrong database')
    c.close()
    execution_id=None
    try:
        execution_id, nid=create_test_notification()
        task=claim_notification(nid)
        assert recover_stale_notifications('CONSOLE', notification_id=nid)==0
        for attempt in range(1,4):
            c=get_connection()
            with c.cursor() as s:
                s.execute('SELECT DATABASE() AS db')
                if s.fetchone()['db'] != 'opspilot_test': raise RuntimeError('Wrong database')
                s.execute('UPDATE JOB_NOTIFICATION_HISTORY SET PROCESSING_STARTED_AT=DATE_SUB(NOW(3), INTERVAL 600 SECOND) WHERE ID=%s',(nid,))
            c.commit(); c.close()
            assert recover_stale_notifications('CONSOLE', notification_id=nid)==1
            assert complete_notification(nid,task['CLAIM_TOKEN'],True) is False
            row=get_notification(nid)
            assert row['RETRY_COUNT']==attempt
            assert row['NOTIFICATION_STATUS']==('EXHAUSTED' if attempt==3 else 'FAILED')
            assert row['CLAIM_TOKEN'] is None
            task=claim_notification(nid)
            assert (task is None)==(attempt==3)
        print('[TEST] ALL PASS: JOB-E2E-10F')
    finally:
        if execution_id: cleanup(execution_id)

if __name__ == "__main__":
    main()
