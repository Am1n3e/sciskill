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
