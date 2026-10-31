"""Demonstrate that only the copied PDF reaches product extraction and verification."""

import builtins
import io
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def pdf_only(monkeypatch, protected):
    original_open = builtins.open
    original_io_open = io.open
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

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", checked(original_open))
        patch.setattr(io, "open", checked(original_io_open))
        yield
