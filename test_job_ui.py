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


if __name__ == '__main__':
    unittest.main()
