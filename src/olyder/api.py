"""Optional authenticated loopback read API. No builder/model/command endpoint."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer

from .config import load_spec
from .diagnostics import doctor
from .engine import plan, verify_once
from .privacy import redact_values


class _LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer normally reverse-resolves its own bound address. This fixed
        # loopback-only service needs no DNS; an unavailable resolver must not
        # hold up startup (notably on macOS hosts).
        TCPServer.server_bind(self)
        self.server_name='127.0.0.1'
        self.server_port=self.server_address[1]


def dispatch(path, supplied_token, token, workspace):
    if not token or not hmac.compare_digest(supplied_token,token):
        return 401,{'error':'unauthorized'}
    if path=='/v1/doctor':
        return 200,doctor()
    if path not in ('/v1/plan','/v1/verify'):
        return 404,{'error':'unknown read endpoint'}
    root=Path(workspace).resolve()
    spec=load_spec(root/'olyder.json')
    if spec.root!=root:
        return 403,{'error':'workspace boundary violation'}
    return 200,plan(spec) if path.endswith('plan') else verify_once(spec)


def create_server(workspace, *, token, port=8765):
    """Construct a loopback server; callers own its shutdown/close lifecycle.

    Port 0 lets the OS allocate an available port without bind/close races.
    """
    if len(token)<24:
        raise ValueError('Set a local API token of at least 24 characters')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get('Origin'):
                status,data=403,{'error':'browser origins are not authorized'}
            else:
                try:
                    status,data=dispatch(self.path,self.headers.get('Authorization','').removeprefix('Bearer '),token,workspace)
                except (OSError,ValueError,RuntimeError):
                    status,data=400,{'error':'invalid workspace or request'}
            encoded=json.dumps(redact_values(data)).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(encoded)))
            self.end_headers();self.wfile.write(encoded)

        def log_message(self,*args):
            pass  # Never log authorization headers or workspace contents.
    return _LoopbackServer(('127.0.0.1',port),Handler)


def serve(workspace, *, token, port=8765):
    with create_server(workspace,token=token,port=port) as server:
        server.serve_forever()
