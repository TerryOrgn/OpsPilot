import os
import unittest
from unittest.mock import MagicMock, patch

from api import job_dashboard
import job_ui_service as service
import job_ui

class UITests(unittest.TestCase):

    def test_unknown_record_rejected(self):
        with self.assertRaises(ValueError):
            service.action('success', 'unowned')

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            service.action('delete', '')

    def test_page_has_core_actions(self):
        for word in ('创建失败 JOB', '运行监控', '发送通知', '标记成功'):
            self.assertIn(word, (job_ui.WEB_ROOT / 'index.html').read_text())

    def test_dashboard_uses_isolated_test_database(self):
        config = {
            "MYSQL_DATABASE": "opspilot",
            "DASHBOARD_MYSQL_DATABASE": "opspilot_test",
            "DASHBOARD_OPSPILOT_EXPECTED_DATABASE": "opspilot_test",
            "DASHBOARD_OPSPILOT_MYSQL_TLS": "1",
            "DASHBOARD_MYSQL_HOST": "aiven.example",
        }
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [[{"ID": 1}], [], []]
        with patch.dict(os.environ, config, clear=True), patch(
            "api.job_dashboard.db.get_connection", return_value=connection
        ) as connect:
            self.assertEqual(job_dashboard.dashboard_state(), {
                "jobs": [{"ID": 1}], "alerts": [], "notifications": [],
            })
        connect.assert_called_once_with(env_prefix="DASHBOARD_")
        connection.close.assert_called_once()

    def test_scoped_scan_rejects_default_checkpoint(self):
        with self.assertRaises(ValueError):
            service.job_monitor.monitor_jobs(checkpoint_name="JOB_MONITOR", execution_id="fixture")


class AIAnalysisTests(unittest.TestCase):
    def test_allowlisted_evidence_and_model_fallback(self):
        import json
        from unittest.mock import Mock
        from job_ai_analysis import analyze_job_abnormalities

        result = dict(schema_version="1.1", tool_name="get_recent_abnormal_jobs",
                      jobs=[{"status": "FAILED", "duration_seconds": 42,
                             "error_message": "private"}], total_abnormal_count=1,
                      returned_count=1, abnormal_count=1, truncated=False)
        client = Mock()
        create = client.with_options.return_value.responses.create
        create.return_value.output_text = '{"possible_causes":["可能超时"],"next_steps":["查看日志"]}'
        report = analyze_job_abnormalities(result, client=client, model="fake")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(json.loads(create.call_args.kwargs["input"]),
                         [{"row": 1, "status": "FAILED", "duration_seconds": 42}])
        client.with_options.assert_called_once_with(timeout=10, max_retries=0)
        expected_fallback = {"status": "unavailable", "facts": report["facts"]}

        for output in ("{}", "{invalid JSON"):
            with self.subTest(output=output):
                create.return_value.output_text = output
                self.assertEqual(
                    analyze_job_abnormalities(result, client=client, model="fake"),
                    expected_fallback,
                )

        for error in (TimeoutError, ConnectionError):
            with self.subTest(error=error):
                create.side_effect = error
                self.assertEqual(
                    analyze_job_abnormalities(result, client=client, model="fake"),
                    expected_fallback,
                )

        self.assertEqual(analyze_job_abnormalities(result, client=None, model=None), expected_fallback)


if __name__ == '__main__':
    unittest.main()
