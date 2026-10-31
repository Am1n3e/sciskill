"""Demonstrate that only the copied PDF reaches product extraction and verification."""

import builtins
import io
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

_BOOTSTRAP = """
import builtins
import io
import json
import os
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
"""


@contextmanager
def pdf_only(monkeypatch, protected):
    original_open, original_io_open = builtins.open, io.open
    roots = [Path(root).resolve() for root in protected]

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
            yield
