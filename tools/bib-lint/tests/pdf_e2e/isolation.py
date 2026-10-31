"""Demonstrate that only the copied PDF reaches product extraction and verification."""

import builtins
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

_BOOTSTRAP = """
import builtins
import io
import json
import os
import socket
from pathlib import Path
_roots = [Path(root).resolve() for root in json.loads(os.environ["SCISKILL_PDF_TEST_GUARD"])]
def _guard(opener):
    def checked(file, *args, **kwargs):
        if not isinstance(file, int):
            path = Path(file).resolve()
            if path.suffix.lower() in {".bib", ".bbl", ".aux"} or any(
                path.is_relative_to(root) for root in _roots
            ):
                raise AssertionError("Product attempted to read a harness input: " + str(path))
        return opener(file, *args, **kwargs)
    return checked
builtins.open = _guard(builtins.open)
io.open = _guard(io.open)
def _no_network(*args, **kwargs):
    raise AssertionError("Unexpected parser network request")
socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network
socket.gethostbyname = _no_network
"""


@contextmanager
def pdf_only(monkeypatch, protected):
    original_open, original_io_open = builtins.open, io.open
    original_run = subprocess.run
    roots = [Path(root).resolve() for root in protected]
    guarded_workers = []

    def guarded_run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and command[0] == sys.executable and "-c" in command:
            script_index = command.index("-c") + 1
            if "bib_lint.pdf_input.worker" in command[script_index]:
                command = list(command)
                command[script_index] = _BOOTSTRAP + "\n" + command[script_index]
                guarded_workers.append(command)
        return original_run(command, *args, **kwargs)

    def checked(opener):
        def open_file(file, *args, **kwargs):
            if not isinstance(file, int):
                path = Path(file).resolve()
                if path.suffix.lower() in {".bib", ".bbl", ".aux"} or any(
                    path.is_relative_to(root) for root in roots
                ):
                    raise AssertionError(f"Product attempted to read a harness input: {path}")
            return opener(file, *args, **kwargs)

        return open_file

    with tempfile.TemporaryDirectory(prefix="sciskill-pdf-test-guard-") as temporary:
        (Path(temporary) / "sitecustomize.py").write_text(_BOOTSTRAP)
        with monkeypatch.context() as patch:
            patch.setenv("SCISKILL_PDF_TEST_GUARD", json.dumps([str(root) for root in roots]))
            patch.setenv("PYTHONPATH", temporary + os.pathsep + os.environ.get("PYTHONPATH", ""))
            patch.setattr(builtins, "open", checked(original_open))
            patch.setattr(io, "open", checked(original_io_open))
            patch.setattr(subprocess, "run", guarded_run)
            yield guarded_workers
