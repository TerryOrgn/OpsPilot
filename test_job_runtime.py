import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import scheduler
from job_runtime import RuntimeConfig, run_notification_batch

class RuntimeTests(unittest.TestCase):
    def test_retry_delay_and_batch_limit_query(self):
        from unittest.mock import MagicMock
        from job_runtime import pending_ids
        connection=MagicMock()
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value=[{'ID':7}]
        with patch('job_runtime.get_connection',return_value=connection):
            self.assertEqual(pending_ids(RuntimeConfig(batch=2,retry_seconds=120)),[7])
        sql,args=cursor.execute.call_args.args
        self.assertIn('UPDATED_AT <=',sql)
        self.assertEqual(args,(None,None,120,2))
        connection.close.assert_called_once()

    def test_bad_config(self):
        with patch.dict(os.environ, {'OPSPILOT_NOTIFICATION_BATCH':'0'}):
            with self.assertRaises(ValueError): RuntimeConfig.from_env()
    def test_batch_never_retries_same_id_in_cycle(self):
        with patch('job_runtime.recover_stale_notifications',return_value=0), patch('job_runtime.pending_ids',return_value=[1,2]), patch('job_runtime.send_console_notification',side_effect=[RuntimeError('private'),True]) as send, patch('job_runtime.backlog',return_value={'PENDING':0}):
            result=run_notification_batch(RuntimeConfig())
        self.assertEqual(send.call_count,2)
        self.assertEqual(result['failed'],1)
        self.assertEqual(result['sent'],1)
    def test_stale_candidate_preserves_retry_cooldown_when_claimed(self):
        with (
            patch('job_runtime.recover_stale_notifications', return_value=0),
            patch('job_runtime.pending_ids', return_value=[7]),
            patch('job_runtime.backlog', return_value={'FAILED': 1}),
            patch('notification_worker.claim_notification', return_value=None) as claim,
        ):
            result = run_notification_batch(RuntimeConfig(retry_seconds=120))
        claim.assert_called_once_with(7, retry_seconds=120)
        self.assertEqual(result['skipped'], 1)

    def test_both_jobs_registered(self):
        service=scheduler.build_scheduler(RuntimeConfig())
        self.assertEqual({j.id for j in service.get_jobs()},{'opspilot_job_monitor','opspilot_notifications'})
        self.assertTrue(all(j.max_instances==1 and j.coalesce for j in service.get_jobs()))
    def test_notification_events_do_not_change_monitor_stats(self):
        before=dict(scheduler.monitor_status)
        scheduler.on_job_event(SimpleNamespace(job_id='opspilot_notifications',code=8192,exception=RuntimeError('secret')))
        self.assertEqual(before,scheduler.monitor_status)

class SafetyTests(unittest.TestCase):
    def test_database_mismatch_never_connects(self):
        import db
        with patch.dict(os.environ, {'MYSQL_DATABASE':'opspilot','OPSPILOT_EXPECTED_DATABASE':'opspilot_test'}), patch('db.pymysql.connect') as connect:
            with self.assertRaises(RuntimeError): db.get_connection()
            connect.assert_not_called()
    def test_redacted_exception(self):
        import logging
        from job_runtime import SecretRedactingFormatter
        with patch.dict(os.environ, {'MYSQL_PASSWORD':'fixture-private-value'}):
            record=logging.LogRecord('test',40,'',0,'failed fixture-private-value',(),None)
            self.assertNotIn('fixture-private-value',SecretRedactingFormatter().format(record))
    def test_sigterm_shutdown_waits(self):
        with patch('scheduler.signal.signal') as signal, patch('scheduler.build_scheduler') as build:
            service=build.return_value
            service.running=True
            def start(): signal.call_args_list[0].args[1](15,None)
            service.start.side_effect=start
            scheduler.main()
            service.shutdown.assert_called_once_with(wait=True)

if __name__=='__main__': unittest.main()
