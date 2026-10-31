"""The test-only guard also protects compiler/source truth from parser subprocesses."""

import subprocess
import sys

import pytest
from pdf_e2e.isolation import pdf_only


def test_pdf_only_guard_covers_parent_and_worker_reads(tmp_path, monkeypatch):
    source = tmp_path / "hidden.bib"
    source.write_text("secret source")
    with pdf_only(monkeypatch, [source.parent]):
        with pytest.raises(AssertionError, match="harness input"):
            source.read_text()
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path(" + repr(str(source)) + ").read_text()",
            ],
            capture_output=True,
            text=True,
        )
    assert process.returncode != 0
    assert "harness input" in process.stderr


def test_parser_worker_cannot_make_network_requests(tmp_path, monkeypatch):
    with pdf_only(monkeypatch, [tmp_path]):
        process = subprocess.run(
            [sys.executable, "-c", "import socket; socket.socket().connect(('127.0.0.1', 9))"],
            capture_output=True,
            text=True,
        )
    assert process.returncode != 0
    assert "Unexpected parser network" in process.stderr


def test_guard_is_injected_into_isolated_real_parser_bootstrap(tmp_path, monkeypatch):
    source = tmp_path / "hidden.bib"
    source.write_text("secret source")
    script = (
        "# bib_lint.pdf_input.worker\nfrom pathlib import Path; Path("
        + repr(str(source))
        + ").read_text()"
    )
    with pdf_only(monkeypatch, [tmp_path]) as guarded:
        process = subprocess.run(
            [sys.executable, "-I", "-c", script], capture_output=True, text=True
        )
    assert process.returncode != 0
    assert "harness input" in process.stderr
    assert len(guarded) == 1
