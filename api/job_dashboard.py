"""Password-protected, read-only dashboard for the Aiven test database."""

import hmac
import json
import logging
import os
from base64 import b64encode
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import db

WEB_ROOT = Path(__file__).resolve().parents[1] / "job_ui_web"
ASSETS = {
    "/": ("index.html", "text/html"),
    "/assets/styles.css": ("styles.css", "text/css"),
    "/assets/app.js": ("app.js", "text/javascript"),
}


def dashboard_state():
    if (
        os.getenv("MYSQL_DATABASE") != "opspilot_test"
        or os.getenv("OPSPILOT_EXPECTED_DATABASE") != "opspilot_test"
        or os.getenv("OPSPILOT_MYSQL_TLS") != "1"
    ):
        raise RuntimeError("Dashboard requires a verified TLS connection to opspilot_test")
    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            result = {}
            for key, sql in (
                ("jobs", "SELECT EXECUTION_ID,JOB_NAME,STATUS,START_TIME,END_TIME FROM JOB_EXECUTION_LOG ORDER BY ID DESC LIMIT 100"),
                ("alerts", "SELECT ID,EXECUTION_ID,ALERT_TYPE,ALERT_STATUS,DETECT_COUNT FROM JOB_ALERT_HISTORY ORDER BY ID DESC LIMIT 100"),
                ("notifications", "SELECT n.ID,a.EXECUTION_ID,n.NOTIFICATION_STATUS,n.RETRY_COUNT FROM JOB_NOTIFICATION_HISTORY n JOIN JOB_ALERT_HISTORY a ON a.ID=n.ALERT_ID ORDER BY n.ID DESC LIMIT 100"),
            ):
                cursor.execute(sql)
                result[key] = cursor.fetchall()
        return result
    finally:
        connection.close()


class handler(BaseHTTPRequestHandler):
    def reply(self, status, data, content_type="application/json", *, challenge=False):
        body = data if isinstance(data, bytes) else json.dumps(data, default=str, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        if challenge:
            self.send_header("WWW-Authenticate", 'Basic realm="OpsPilot"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        password = os.getenv("OPSPILOT_DASHBOARD_PASSWORD")
        if not password:
            return self.reply(503, {"error": "监控页面尚未配置访问密码"})
        expected = b"Basic " + b64encode(("opspilot:" + password).encode())
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
            return self.reply(401, {"error": "请登录"}, challenge=True)

        request = urlsplit(self.path)
        params = parse_qs(request.query)
        path = request.path
        if path == "/api/job_dashboard":
            view = params.get("view", [""])[0]
            asset = params.get("asset", [""])[0]
            path = {"home": "/", "state": "/api/state", "asset": "/assets/" + asset}.get(view, path)
        if path == "/api/state":
            try:
                return self.reply(200, dashboard_state())
            except Exception as exc:
                code = exc.args[0] if exc.args and type(exc.args[0]) is int else None
                cause = getattr(exc, "original_exception", None) or exc.__cause__ or exc.__context__
                logging.error(
                    "Dashboard read failed type=%s code=%s cause=%s",
                    type(exc).__name__,
                    code,
                    type(cause).__name__ if cause else None,
                )
                return self.reply(503, {"error": "暂时无法读取测试库，请检查云端连接配置"})
        if path in ASSETS:
            name, content_type = ASSETS[path]
            body = (WEB_ROOT / name).read_bytes()
            if path == "/":
                body = body.replace(b'<body>', b'<body data-dashboard="cloud">')
                body = body.replace(b'<section id="workbench">', b'<section id="workbench" hidden>')
                body = body.decode().replace("本地验收台", "云端监控").replace(
                    "JOB 监控验收台", "JOB 监控台"
                ).replace("本地测试库", "Aiven 测试库").replace(
                    "创建任务 → 检测告警 → 发送通知 → 恢复验证", "查看任务执行、告警与通知状态"
                ).encode()
            return self.reply(200, body, content_type)
        return self.reply(404, {"error": "页面不存在"})
