"""Installed-viewer readiness must use the same direct loopback route as the browser."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_package import wait_for_viewer


class RunningProcess:
    def poll(self):
        return None


@contextmanager
def endpoint(status=200, body=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            raw = json.dumps(body or {"summary": None, "csrf": "session"}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join()


def test_readiness_ignores_environment_and_macos_proxy_discovery(tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("viewer started\n")
    with endpoint() as (viewer, requests), endpoint(502, {"error": "proxy"}) as (proxy, proxied):
        monkeypatch.setenv("HTTP_PROXY", proxy)
        monkeypatch.setenv("http_proxy", proxy)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        assert wait_for_viewer(RunningProcess(), viewer, log, timeout=0.4)["csrf"] == "session"
    assert requests == ["/api/state"]
    assert proxied == []


def test_readiness_failure_includes_last_http_response_and_server_log(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("startup diagnostic: address is bound\n")
    with endpoint(422, {"error": "session failed"}) as (viewer, _):
        with pytest.raises(AssertionError) as error:
            wait_for_viewer(RunningProcess(), viewer, log, timeout=0.02)
    message = str(error.value)
    assert "422" in message and "session failed" in message
    assert "startup diagnostic: address is bound" in message


def test_readiness_reports_early_process_exit_and_stderr(tmp_path):
    class ExitedProcess:
        def poll(self):
            return 7

    log = tmp_path / "server.log"
    log.write_text("ImportError: missing installed asset\n")
    with pytest.raises(AssertionError, match="missing installed asset") as error:
        wait_for_viewer(ExitedProcess(), "http://127.0.0.1:1", log, timeout=1)
    assert "7" in str(error.value)


def test_success_status_without_state_shape_does_not_claim_readiness(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("server running\n")
    with endpoint(200, {"error": "wrong API"}) as (viewer, _):
        with pytest.raises(AssertionError, match="wrong API"):
            wait_for_viewer(RunningProcess(), viewer, log, timeout=0.02)
