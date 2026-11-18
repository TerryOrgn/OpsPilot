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
from job_ai_analysis import analyze_job_abnormalities

WEB_ROOT = Path(__file__).resolve().parents[1] / "job_ui_web"
ASSETS = {
    "/": ("index.html", "text/html"),
    "/assets/styles.css": ("styles.css", "text/css"),
    "/assets/app.js": ("app.js", "text/javascript"),
}


def dashboard_read_error(exc):
    """Return fixed messages without exposing connection details."""
    import ssl

    chain = []
    current = exc
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = (getattr(current, "original_exception", None)
                   or current.__cause__ or current.__context__)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return "测试库 TLS 证书校验失败，请检查 CA 证书和主机名"
    code = exc.args[0] if exc.args and type(exc.args[0]) is int else None
    messages = {
        1045: "测试库账号认证失败，请检查数据库用户名和密码",
        1044: "测试库访问被拒绝，请检查账号授权",
        1142: "测试库表操作被拒绝，请检查看板只读权限",
        2003: "暂时无法连接测试库，请检查主机、端口及网络",
    }
    if code in messages:
        return messages[code]
    if isinstance(exc, RuntimeError):
        return "测试库连接配置校验失败，请检查库名、TLS 开关和主机配置"
    return "暂时无法读取测试库，请查看服务端错误日志"


def dashboard_connection():
    # Keep existing test deployments working while allowing a separate read-only account.
    prefix = "DASHBOARD_" if any(key.startswith("DASHBOARD_MYSQL_") for key in os.environ) else ""
    if (
        os.getenv(prefix + "MYSQL_DATABASE") != "opspilot_test"
        or os.getenv(prefix + "OPSPILOT_EXPECTED_DATABASE") != "opspilot_test"
        or os.getenv(prefix + "OPSPILOT_MYSQL_TLS") != "1"
    ):
        raise RuntimeError("Dashboard requires a verified TLS connection to opspilot_test")
    if prefix and not os.getenv(prefix + "MYSQL_HOST"):
        raise RuntimeError("Dashboard requires an explicit database host")
    return db.get_connection(env_prefix=prefix)


def dashboard_state():
    connection = dashboard_connection()
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

    def authorized(self):
        password = os.getenv("OPSPILOT_DASHBOARD_PASSWORD")
        if not password:
            self.reply(503, {"error": "监控页面尚未配置访问密码"})
            return False
        expected = b"Basic " + b64encode(("opspilot:" + password).encode())
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
            self.reply(401, {"error": "请登录"}, challenge=True)
            return False
        return True

    def do_POST(self):
        if not self.authorized():
            return
        if urlsplit(self.path).path != "/api/job_dashboard":
            return self.reply(404, {"error": "页面不存在"})
        if self.headers.get("X-OpsPilot-Action") != "analyze":
            return self.reply(403, {"error": "请求未获授权"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 256:
                raise ValueError
            alert_id = json.loads(self.rfile.read(size))["alert_id"]
            if type(alert_id) is not int or not 0 < alert_id < 2**63:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self.reply(400, {"error": "无效告警编号"})
        try:
            connection = dashboard_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT j.STATUS, a.ALERT_TYPE, TIMESTAMPDIFF(SECOND,j.START_TIME,COALESCE(j.END_TIME,NOW(3))) AS DURATION_SECONDS FROM JOB_ALERT_HISTORY a JOIN JOB_EXECUTION_LOG j "
                        "ON j.EXECUTION_ID=a.EXECUTION_ID WHERE a.ID=%s "
                        "AND a.ALERT_STATUS='OPEN' AND ((a.ALERT_TYPE='JOB_FAILED' AND j.STATUS='FAILED') OR (a.ALERT_TYPE='JOB_TIMEOUT' AND j.STATUS IN ('RUNNING','SUCCESS')))", (alert_id,),
                    )
                    row = cursor.fetchone()
            finally:
                connection.close()
        except Exception as exc:
            logging.error("Dashboard analysis read failed type=%s", type(exc).__name__)
            return self.reply(503, {"error": "暂时无法读取测试库"})
        if not row:
            return self.reply(404, {"error": "此告警当前不可分析"})
        model = os.getenv("DASHBOARD_AI_MODEL")
        key = os.getenv("DASHBOARD_AI_API_KEY")
        client = None
        if model and key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
            except Exception as exc:
                logging.warning("Dashboard AI client unavailable type=%s", type(exc).__name__)
        result = analyze_job_abnormalities(
            dict(schema_version="1.1", tool_name="get_recent_abnormal_jobs",
                 jobs=[{"status": row["STATUS"], "alert_type": row["ALERT_TYPE"], "duration_seconds": row.get("DURATION_SECONDS")}], total_abnormal_count=1,
                 returned_count=1, abnormal_count=1, truncated=False),
            client=client, model=model,
        )
        return self.reply(200, result)

    def do_GET(self):
        if not self.authorized():
            return
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
                return self.reply(503, {"error": dashboard_read_error(exc)})
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
