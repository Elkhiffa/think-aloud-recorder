"""On-demand authenticated loopback bridge; never scans libraries or uploads media."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import secrets
import threading

from app_paths import application_root

ENDPOINT = 'state/vocabulary-agent.json'
MAX_MESSAGE = 2 * 1024 * 1024


class VocabularyServer:
    def __init__(self, root, dispatch):
        self.root = application_root(root)
        self.token = secrets.token_hex(32)
        token = self.token

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *_):
                pass  # No credentials or private vocabulary in access logs.

            def do_POST(self):
                if (self.path != '/vocabulary' or self.headers.get('Origin') is not None
                        or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'
                        or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)):
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if (not 0 < length <= MAX_MESSAGE or self.headers.get('Transfer-Encoding')
                            or self.headers.get_content_type() != 'application/json'):
                        raise ValueError('请求大小或格式无效。')
                    request = json.loads(self.rfile.read(length))
                    result = dispatch(request)
                except (OSError, ValueError, TypeError):
                    result = dict(ok=False, code='INVALID_REQUEST', error='本机词库请求无效或读取超时。')
                data = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                try:
                    self.wfile.write(data)
                except OSError:
                    pass  # An apply receipt can always be recovered by read-back/retry.

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1},
                                       name='vocabulary-agent', daemon=True)
        self.path = self.root / ENDPOINT

    def start(self):
        from recorder import write
        try:
            write(self.path, dict(protocol=1, port=self.server.server_port, token=self.token))
            self.thread.start()
        except Exception:
            self.server.server_close()
            raise
        return self

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(2)
        self.server.server_close()
        try:
            if json.loads(self.path.read_text(encoding='utf-8')).get('token') == self.token:
                self.path.unlink()
        except (OSError, ValueError):
            pass


def request(root, payload):
    """CLI sends only to its own install's live endpoint, bypassing network proxies."""
    path = application_root(root) / ENDPOINT
    try:
        if path.stat().st_size > 4096:
            raise ValueError()
        endpoint = json.loads(path.read_text(encoding='utf-8'))
        port, token = endpoint['port'], endpoint['token']
        if (endpoint.get('protocol') != 1 or type(port) is not int or not 0 < port < 65536
                or not isinstance(token, str) or len(token) != 64
                or any(char not in '0123456789abcdef' for char in token)):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        return dict(ok=False, code='APP_UNAVAILABLE', error='请先启动支持词库接口的 Think Aloud（0.7.5 或更新版本）；不会直接改写离线配置。')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(body) > MAX_MESSAGE:
            raise ValueError('词库请求超过 2 MB。')
        connection.request('POST', '/vocabulary', body=body,
                           headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(MAX_MESSAGE + 1)
        if response.status != 200 or len(data) > MAX_MESSAGE:
            raise ValueError('本机词库接口响应无效。')
        return json.loads(data)
    except (OSError, http.client.HTTPException, ValueError):
        return dict(ok=False, code='RESPONSE_UNCONFIRMED',
                    error='未收到有效回执。请确认应用已运行；应用请求可能已生效，请回读或重试同一计划，不要直接改配置。')
    finally:
        connection.close()
