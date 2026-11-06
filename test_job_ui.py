import unittest
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
if __name__ == '__main__':
    unittest.main()
