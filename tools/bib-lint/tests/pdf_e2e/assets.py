"""Fetch pinned official assets and stage only checksum-verified members."""

import hashlib
import io
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import httpx


def _checked(raw: bytes, expected: str, name: str) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Unexpected checksum: {name}")


def _member_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not path.parts:
        raise ValueError(f"Unsafe archive member: {value}")
    return path


def prepare_asset(asset_id: str, pin: dict, cache: Path) -> Path:
    """Verify on every use; extraction cannot trust a previously populated cache."""
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"{asset_id}.zip"
    raw = archive.read_bytes() if archive.exists() else _download(pin)
    _checked(raw, pin["sha256"], asset_id)
    if len(raw) != pin["bytes"]:
        raise ValueError(f"Unexpected archive size: {asset_id}")
    members = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        for member in pin["files"]:
            relative = _member_path(member["path"])
            source = _member_path(pin["root"] + member["path"])
            info = zipped.getinfo(str(source))
            if info.file_size > 10_000_000 or info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError(f"Unsafe archive member: {source}")
            content = zipped.read(info)
            _checked(content, member["sha256"], str(source))
            members[relative] = content
    destination = cache / pin["sha256"]
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        stage = Path(temporary) / "members"
        stage.mkdir()
        for relative, content in members.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)
    if not archive.exists():
        archive.write_bytes(raw)
    return destination


def _download(pin: dict) -> bytes:
    with httpx.stream("GET", pin["url"], follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        chunks = bytearray()
        for chunk in response.iter_bytes():
            chunks.extend(chunk)
            if len(chunks) > pin["bytes"]:
                raise ValueError(f"Unexpected archive size: {pin['url']}")
    return bytes(chunks)


def verified_asset(pin: dict, cache: Path) -> Path:
    """Offline builds verify the staged files too, including cache hits."""
    destination = cache / pin["sha256"]
    for member in pin["files"]:
        path = destination / _member_path(member["path"])
        _checked(path.read_bytes(), member["sha256"], str(path))
    return destination
