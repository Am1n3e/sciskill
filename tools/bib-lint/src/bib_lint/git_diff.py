"""Select new BibTeX identities from immutable Git objects without checkout or execution."""

import subprocess
from dataclasses import replace
from pathlib import Path

from bib_lint.parser import parse_string


def _git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(
            "Git comparison failed: " + result.stderr.decode("utf-8", "replace").strip()
        )
    return result.stdout


def _revision(root, ref):
    return (
        _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        .decode()
        .strip()
    )


def _bibliographies(root, revision):
    files = {}
    for record in _git(root, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        path = name.decode("utf-8")
        if Path(path).suffix.lower() == ".bib":
            mode, kind, oid = metadata.decode().split()
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"Bibliography must be a regular file: {revision}:{path}")
            files[path] = oid
    return files


def _parse(root, oid, source, encoding):
    return parse_string(_git(root, "cat-file", "blob", oid).decode(encoding), source_name=source)


def added_bibliography(source, base, head=None, *, encoding="utf-8"):
    source = Path(source).absolute()
    anchor = source.parent
    while not anchor.is_dir():
        anchor = anchor.parent
    root = Path(_git(anchor, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    path = (source.parent.resolve() / source.name).relative_to(root).as_posix()
    base_oid, head_oid = _revision(root, base), _revision(root, head or "HEAD")
    merge_base = _git(root, "merge-base", base_oid, head_oid).decode().strip()
    head_files = _bibliographies(root, head_oid)
    if path not in head_files:
        raise ValueError(f"Bibliography is not tracked at the PR head: {path}")
    previous = set()
    for old_path, oid in _bibliographies(root, merge_base).items():
        bib = _parse(root, oid, f"{merge_base}:{old_path}", encoding)
        previous.update(key.casefold() for key in bib.entries)
    current = _parse(root, head_files[path], str(source), encoding)
    entries = {
        key: entry for key, entry in current.entries.items() if key.casefold() not in previous
    }
    selection = {
        "kind": "added",
        "base": base_oid,
        "merge_base": merge_base,
        "head": head_oid,
        "path": path,
        "keys": list(entries),
    }
    return replace(current, entries=entries), selection
