"""Atomic JSON files and a stable advisory lock shared by parse and verify."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def report_paths(path):
    path = Path(path)
    final = path.with_name(path.name[:-9] + ".json") if path.name.endswith(".tmp.json") else path
    return final, final.with_name(final.stem + ".tmp.json")


@contextmanager
def report_lock(final):
    # Never unlink this sidecar: all writers must lock the same inode across renames.
    lock_path = Path(str(final) + ".lock")
    with lock_path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"Report is already in use: {final}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json(output, payload):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
