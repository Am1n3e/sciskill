"""Offline by default, with logical time for HTTP pacing and retries."""

import socket
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        name = Path(str(item.fspath)).name
        category = (
            "package"
            if name == "test_package.py"
            else "ui"
            if name in {"test_viewer.py", "test_agent_review.py", "test_jobs.py", "test_ui.py"}
            else "workflow"
            if name
            in {
                "test_resume.py",
                "test_audit.py",
                "test_cli.py",
                "test_provider_workflow.py",
            }
            else "unit"
        )
        item.add_marker(getattr(pytest.mark, category))


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch):
    from bib_lint.verification import http

    clock = [100.0]
    monkeypatch.setattr(
        http,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock[0],
            sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
            time=time.time,
        ),
    )
    original = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError(f"Unexpected external network connection: {address}")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
