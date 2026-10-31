"""Loopback server: expose only packaged assets and validated workspace data."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from socketserver import TCPServer
from urllib.parse import urlsplit

from .workspace import load_workspace

ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/styles.css": ("styles.css", "text/css"),
}


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # The bound numeric loopback address needs no reverse-DNS public name.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.socket.getsockname()[1]


def make_server(workspace, port=0):
    load_workspace(workspace)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Do not allow other origins to read local review content or DNS rebinding.
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            route = urlsplit(self.path).path
            if route == "/workspace.json":
                self.send_workspace()
            elif route in ASSETS:
                name, mime = ASSETS[route]
                self.send_bytes(
                    files("rebuttal_desk").joinpath("static", name).read_bytes(), mime
                )
            else:
                self.send_error(404)

        def send_workspace(self):
            try:
                body = json.dumps(load_workspace(workspace)).encode()
            except (ValueError, OSError):
                self.send_error(
                    422, "Workspace validation failed; run rebuttal-desk validate"
                )
                return
            self.send_bytes(body, "application/json")

        def send_bytes(self, body, mime):
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return LoopbackServer(("127.0.0.1", port), Handler)
