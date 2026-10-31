"""Stage the vendored official template subset without asset network access."""

import hashlib
import shutil
import tempfile
from pathlib import Path, PurePosixPath

VENDORED_ROOT = Path(__file__).resolve().parents[1] / "assets/pdf"


def _checked(raw: bytes, expected: str, name: str) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Unexpected checksum: {name}")


def _member_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not path.parts:
        raise ValueError(f"Unsafe template member: {value}")
    return path


def _members(pin: dict) -> list[dict]:
    members = pin["files"] + pin.get("notices", [])
    paths = [_member_path(member["path"]) for member in members]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate template member paths")
    return members


def _read_member(root: Path, member: dict) -> bytes:
    path = root
    for part in ("", *_member_path(member["path"]).parts):
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Unsafe template symlink: {path}")
    if not path.is_file():
        raise ValueError(f"Missing template member: {path}")
    if path.stat().st_size > 10_000_000:
        raise ValueError(f"Oversized template member: {path}")
    raw = path.read_bytes()
    _checked(raw, member["sha256"], str(path))
    return raw


def _destination(pin: dict, cache: Path) -> Path:
    digest = pin["sha256"]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("Invalid archive SHA-256 in template provenance")
    return cache / digest


def prepare_asset(asset_id: str, pin: dict, cache: Path) -> Path:
    """Reverify committed source bytes even when an old staged cache exists."""
    destination = _destination(pin, cache)
    identifier = _member_path(asset_id)
    if len(identifier.parts) != 1 or VENDORED_ROOT.is_symlink():
        raise ValueError(f"Unsafe template asset: {asset_id}")
    source = VENDORED_ROOT / identifier
    members = {member["path"]: _read_member(source, member) for member in _members(pin)}
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        stage = Path(temporary) / "members"
        stage.mkdir()
        for relative, raw in members.items():
            target = stage / _member_path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        if destination.is_symlink():
            raise ValueError(f"Unsafe template cache symlink: {destination}")
        if destination.exists():
            shutil.rmtree(destination)
        stage.rename(destination)
    return destination


def verified_asset(pin: dict, cache: Path) -> Path:
    """Offline builds reverify every staged source and original notice."""
    destination = _destination(pin, cache)
    members = _members(pin)
    for member in members:
        _read_member(destination, member)
    expected = {member["path"] for member in members}
    actual = {
        str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()
    }
    if actual != expected:
        raise ValueError(f"Unexpected template cache inventory: {destination}")
    return destination
