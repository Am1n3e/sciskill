"""Rebuttal Desk-style loopback server with bundled assets and local audit APIs."""

import json
import secrets
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlsplit

from bib_lint.viewer.app import ViewerSession
from bib_lint.viewer.jobs import Registry

ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/styles.css": ("styles.css", "text/css"),
}


class ViewerServer(ThreadingHTTPServer):
    def __init__(self, path, port, registry):
        self.registry = registry or Registry()
        self.initial_report = path
        self.sessions = {}
        self.session_guard = threading.RLock()
        super().__init__(("127.0.0.1", port), Handler)

    def session(self, cookie):
        cookies = SimpleCookie()
        cookies.load(cookie or "")
        name = f"bib_lint_{self.server_port}"
        identity = cookies[name].value if name in cookies else ""
        with self.session_guard:
            if identity not in self.sessions:
                identity = secrets.token_urlsafe(24)
                self.sessions[identity] = ViewerSession(self.registry, self.initial_report)
            return self.sessions[identity], f"{name}={identity}; HttpOnly; SameSite=Strict; Path=/"

    def server_close(self):
        super().server_close()
        self.registry.shutdown()


class Handler(BaseHTTPRequestHandler):
    def allowed(self):
        authority = f"127.0.0.1:{self.server.server_port}"
        origin = self.headers.get("Origin")
        if self.headers.get("Host") != authority or origin not in (None, f"http://{authority}"):
            self.send_error(403)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        route = urlsplit(self.path)
        if route.path in ASSETS:
            name, mime = ASSETS[route.path]
            self.send_bytes(files("bib_lint.viewer").joinpath("static", name).read_bytes(), mime)
            return
        self.api_get(route)

    def api_get(self, route):
        session, self.cookie = self.server.session(self.headers.get("Cookie"))
        query = parse_qs(route.query)
        try:
            readers = {
                "/api/state": session.state,
                "/api/reference": lambda: session.detail(query.get("key", [""])[0]),
                "/api/response": lambda: session.response(
                    query.get("key", [""])[0], int(query.get("index", ["0"])[0])
                ),
            }
            if route.path not in readers:
                self.send_json({"error": "Not found"}, 404)
                return
            self.send_json(readers[route.path]())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.send_json({"error": str(exc)}, 422)

    def do_POST(self):
        if not self.allowed():
            return
        session, self.cookie = self.server.session(self.headers.get("Cookie"))
        if self.headers.get("X-CSRF-Token") != session.csrf:
            self.send_json({"error": "Reload this page before changing the audit."}, 403)
            return
        if self.path != "/api/action":
            self.send_json({"error": "Not found"}, 404)
            return
        self.api_action(session)

    def api_action(self, session):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536 or self.headers.get("Content-Type") != "application/json":
                raise ValueError("Expected a small JSON action request")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or any(
                not isinstance(v, str) for v in payload.values()
            ):
                raise ValueError("Audit action fields must be text")
            self.send_json(session.action(payload))
        except (OSError, ValueError, KeyError, TypeError, LookupError) as exc:
            self.send_json({"error": str(exc)}, 422)

    def send_json(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json", status)

    def send_bytes(self, body, mime, status=200):
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        if getattr(self, "cookie", None):
            self.send_header("Set-Cookie", self.cookie)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def make_server(path="", port=0, *, registry=None):
    return ViewerServer(path, port, registry)


def serve(path="", port=8501, *, no_browser=False):
    with make_server(path, port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(url, flush=True)
        if not no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
