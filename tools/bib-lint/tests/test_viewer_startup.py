"""The loopback viewer must bind and listen without host-name resolution."""

import socket
import threading

import httpx

from bib_lint.viewer.server import make_server


def test_loopback_viewer_startup_does_not_resolve_reverse_dns(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Loopback viewer startup attempted reverse DNS")

    monkeypatch.setattr(socket, "getfqdn", forbidden)
    monkeypatch.setattr(socket, "gethostbyaddr", forbidden)
    with make_server() as server:
        assert server.server_name == "localhost"
        assert server.server_port == server.socket.getsockname()[1] > 0
        assert server.server_address[0] == "127.0.0.1"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(trust_env=False, timeout=1) as browser:
                response = browser.get(f"http://127.0.0.1:{server.server_port}/api/state")
            assert response.status_code == 200 and response.json()["summary"] is None
        finally:
            server.shutdown()
            thread.join(timeout=2)
