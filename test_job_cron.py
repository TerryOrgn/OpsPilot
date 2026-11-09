import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'job_cron', Path(__file__).with_name('api') / 'job_cron.py'
)
cron = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cron)


class CronTests(unittest.TestCase):
    def test_request_gates(self):
        for env, auth, expected in (
            ({}, '', 401),
            ({'CRON_SECRET': 'test'}, 'Bearer wrong', 401),
            ({'CRON_SECRET': 'test'}, 'Bearer test', 503),
            ({'CRON_SECRET': 'test', 'OPSPILOT_CRON_ENABLED': '1',
              'VERCEL_ENV': 'preview', 'MYSQL_DATABASE': 'opspilot'}, 'Bearer test', 503),
            ({'CRON_SECRET': 'test', 'OPSPILOT_CRON_ENABLED': '1',
              'VERCEL_ENV': 'production', 'MYSQL_DATABASE': 'opspilot'}, 'Bearer test', 503),
            ({'CRON_SECRET': 'test', 'OPSPILOT_CRON_ENABLED': '1',
              'VERCEL_ENV': 'preview', 'MYSQL_DATABASE': 'opspilot_test'}, 'Bearer test', 503),
            ({'CRON_SECRET': 'test', 'OPSPILOT_CRON_ENABLED': '1',
              'VERCEL_ENV': 'preview', 'MYSQL_DATABASE': 'opspilot_test',
              'OPSPILOT_EXPECTED_DATABASE': 'opspilot_test', 'OPSPILOT_MYSQL_TLS': '1',
              'OPSPILOT_PREVIEW_EXECUTION_ID': 'PREVIEW_0123456789abcdef0123'}, 'Bearer test', 200),
        ):
            with self.subTest(expected=expected, env=env), patch.dict(os.environ, env, clear=True), patch.object(cron, 'run_cycle', return_value={'status': 'completed'}) as run:
                request = Mock(headers={'Authorization': auth})
                cron.handler.do_GET(request)
                self.assertEqual(request.reply.call_args.args[0], expected)
                self.assertEqual(run.call_count, int(expected == 200))

    def test_preview_cycle_processes_only_fixture_notifications(self):
        execution_id = "PREVIEW_0123456789abcdef0123"
        env = {
            "VERCEL_ENV": "preview",
            "MYSQL_DATABASE": "opspilot_test",
            "OPSPILOT_EXPECTED_DATABASE": "opspilot_test",
            "OPSPILOT_MYSQL_TLS": "1",
            "OPSPILOT_PREVIEW_EXECUTION_ID": execution_id,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(cron, "configure_logging"),
            patch.object(cron, "check_readiness") as readiness,
            patch.object(cron, "monitor_jobs") as monitor,
            patch.object(cron, "get_connection") as connect,
            patch.object(cron, "get_job_by_execution_id", return_value={"SYSTEM_ID": "PREVIEW_TEST"}),
            patch.object(cron, "run_notification_batch", return_value={"sent": 1}) as send,
            patch.object(cron, "run_with_monitor_lock", side_effect=lambda callback: callback()),
        ):
            connection = connect.return_value
            cursor = Mock()
            connection.cursor.return_value = unittest.mock.MagicMock()
            connection.cursor.return_value.__enter__.return_value = cursor
            cursor.fetchall.return_value = [{"ID": 17}]
            result = cron.run_cycle()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["notifications"][0]["id"], 17)
        self.assertEqual(readiness.call_args.kwargs["checkpoint_name"], execution_id)
        monitor.assert_called_once_with(checkpoint_name=execution_id, execution_id=execution_id)
        self.assertEqual(send.call_args.kwargs, {"notification_id": 17})
        self.assertEqual(send.call_count, 1)
        self.assertEqual(cursor.execute.call_args.args[1][0], execution_id)
        connection.close.assert_called_once()

    def test_one_cycle_executes_inside_lock(self):
        with patch.object(cron, 'check_readiness'), patch.object(cron, 'configure_logging'), patch.object(cron, 'monitor_jobs') as monitor, patch.object(cron, 'run_notification_batch', return_value={'sent': 1}), patch.object(cron, 'run_with_monitor_lock') as lock:
            lock.return_value = False
            self.assertEqual(cron.run_cycle()['status'], 'skipped')
            monitor.assert_not_called()
            lock.side_effect = lambda callback: callback() or True
            self.assertEqual(cron.run_cycle()['notifications'], {'sent': 1})
            monitor.assert_called_once()


if __name__ == '__main__':
    unittest.main()
