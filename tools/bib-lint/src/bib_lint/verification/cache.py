"""Raw response files with a locked SHA-256 manifest and verified reads."""

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from bib_lint.storage import report_lock, write_json


def component(value):
    encoded = quote(str(value), safe="-_")
    return encoded.replace(".", "%2E") if encoded in {".", ".."} else encoded or "_unknown"


class ResponseCache:
    def _load_entry(self, citation_key, prefix, entry, manifest):
        relative = Path(entry.get("path", ""))
        valid_path = (
            len(relative.parts) == 2
            and relative.parts[0] == component(citation_key)
            and relative.name.startswith(prefix)
            and not relative.is_absolute()
        )
        path = self.root / relative
        raw = None
        if valid_path and not path.is_symlink():
            try:
                raw = path.read_bytes()
            except OSError:
                pass
        if raw is None or hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
            if valid_path and (path.is_file() or path.is_symlink()):
                path.unlink()
            manifest["files"].remove(entry)
            write_json(self.manifest, manifest)
            return None
        if time.time() - entry["cached_at"] >= 7 * 86400:
            return None
        return raw, entry

    def _remove_untracked(self, folder, prefix, manifest):
        tracked = {entry.get("path") for entry in manifest["files"] if isinstance(entry, dict)}
        # Untracked raw responses have no trusted checksum and cannot be reused.
        if folder.exists():
            for path in folder.iterdir():
                if path.name.startswith(prefix) and path.is_file():
                    if path.relative_to(self.root).as_posix() not in tracked:
                        path.unlink()

    def __init__(self, root):
        self.root = Path(root)
        self.manifest = self.root / "checksum.json"

    def _manifest(self):
        try:
            data = json.loads(self.manifest.read_text())
            if data.get("algorithm") == "sha256" and isinstance(data.get("files"), list):
                return data
        except (OSError, ValueError, AttributeError):
            pass
        return {"algorithm": "sha256", "files": []}

    def _folder(self, citation_key):
        folder = self.root / component(citation_key)
        if folder.is_symlink():
            raise ValueError(f"Cache citation directory must not be a symlink: {folder}")
        return folder

    def load(self, citation_key, method, request_key):
        if not self.root.exists():
            return None
        with report_lock(self.manifest):
            manifest = self._manifest()
            folder = self._folder(citation_key)
            prefix = component(method) + "_"
            self._remove_untracked(folder, prefix, manifest)
            candidates = [
                entry
                for entry in manifest["files"]
                if isinstance(entry, dict)
                and entry.get("citation_key") == citation_key
                and entry.get("method") == method
                and entry.get("request_key") == request_key
                and entry.get("status_code") == 200
            ]
            if not candidates:
                return None
            entry = max(candidates, key=lambda e: e.get("cached_at", 0))
            return self._load_entry(citation_key, prefix, entry, manifest)

    def save(self, citation_key, method, request_key, url, response):
        self.root.mkdir(parents=True, exist_ok=True)
        raw = response.content  # Decoded HTTP entity bytes; never reserialize or reformat the body.
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or raw.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            extension = "html"
        elif "xml" in content_type or raw.lstrip().startswith(b"<"):
            extension = "xml"
        else:
            try:
                json.loads(raw)
                extension = "json"
            except (ValueError, UnicodeError):
                extension = "txt"
        with report_lock(self.manifest):
            manifest = self._manifest()
            folder = self._folder(citation_key)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = time.time_ns()
            path = folder / f"{component(method)}_{stamp}.{extension}"
            while path.exists():
                stamp += 1
                path = folder / f"{component(method)}_{stamp}.{extension}"
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            entry = {
                "path": path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "citation_key": citation_key,
                "method": method,
                "request_key": request_key,
                "url": url,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "cached_at": time.time(),
                "encoding": response.encoding or "utf-8",
                "status_code": response.status_code,
                "reason": response.reason_phrase,
                "headers": {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"set-cookie", "authorization", "x-api-key"}
                },
            }
            manifest["files"].append(entry)
            write_json(self.manifest, manifest)
            return entry
