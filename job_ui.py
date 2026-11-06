"""Loopback HTTP entry point for the JOB acceptance UI."""
import json
import logging
import os
import secrets
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Lock
from dotenv import load_dotenv
from job_runtime import configure_logging
import job_ui_service as service
WEB_ROOT = Path(__file__).with_name('job_ui_web')
ASSETS = {'/': ('index.html', 'text/html'), '/assets/styles.css': ('styles.css', 'text/css'), '/assets/app.js': ('app.js', 'text/javascript')}
csrf = secrets.token_urlsafe(32)
service_lock = Lock()

class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def reply(self, status, data, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data, default=str, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Local host only'})
        try:
            if self.path in ASSETS:
                filename, mime = ASSETS[self.path]
                body = (WEB_ROOT / filename).read_bytes()
                if self.path == '/':
                    body = body.replace(b'__CSRF__', csrf.encode())
                self.reply(200, body, mime)
            elif self.path == '/api/state':
                with service_lock:
                    state = service.state()
                self.reply(200, state)
            else:
                self.reply(404, {'error': 'Not found'})
        except Exception as exc:
            logging.error('UI read failed type=%s', type(exc).__name__)
            self.reply(500, {'error': '读取失败，请检查本地服务日志'})

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-CSRF-Token') != csrf:
            return self.reply(403, {'error': 'Invalid request token'})
        if self.path != '/api/action':
            return self.reply(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size < 4096:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            with service_lock:
                result = service.action(data['action'], data.get('execution_id', ''))
            self.reply(200, result)
        except (ValueError, KeyError, TypeError, AttributeError):
            self.reply(400, {'error': '请先选择本次会话创建的 JOB，并使用有效操作'})
        except Exception as exc:
            logging.error('UI action failed type=%s', type(exc).__name__)
            self.reply(500, {'error': '操作失败，请检查本地服务日志'})

def main():
    configure_logging('INFO')
    os.environ['MYSQL_DATABASE'] = 'opspilot_test'
    os.environ['OPSPILOT_EXPECTED_DATABASE'] = 'opspilot_test'
    load_dotenv(Path(__file__).with_name('.env'))
    port = int(os.getenv('OPSPILOT_UI_PORT', '8765'))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    try:
        service.initialize()
        print(f"OpsPilot UI: http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
if __name__ == '__main__':
    main()
