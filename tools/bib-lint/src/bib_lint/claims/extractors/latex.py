"""Capture LaTeX sources and seed references using the existing BibTeX parser."""

import re
from dataclasses import asdict
from pathlib import Path

from bib_lint.claims.extractors.tex_syntax import commands, visible_text
from bib_lint.claims.protocols import Extraction, Request, Source
from bib_lint.claims.text import digest
from bib_lint.parser import parse_string


def _read(path: Path, root: Path, kind: str = "latex") -> Source:
    path = path.resolve()
    file = path.relative_to(root).as_posix()
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError(f"Source exceeds 4 MiB limit: {path}")
    raw = path.read_bytes()
    return Source(file, path, raw, raw.decode("utf-8"), f"sources/{file}", {"kind": kind})


def _literal_path(value: str, parent: Path, root: Path, suffix: str) -> Path:
    if not value.strip() or re.search(r"[\\#$]", value):
        raise ValueError(f"Dynamic or empty source path is unsupported: {value!r}")
    path = Path(value.strip())
    if not path.suffix:
        path = path.with_suffix(suffix)
    candidate = root / path
    if not candidate.is_file():
        candidate = parent / path
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Source path escapes project root: {value!r}")
    return candidate


def _walk(path, root, sources, events, bibs, active):
    path = path.resolve()
    if path in active:
        raise ValueError(f"Cyclic LaTeX include: {path}")
    if len(events) > 30000 or len(sources) >= 500 or len(active) >= 100:
        raise ValueError("LaTeX project exceeds file or command limits")
    source = sources.setdefault(path, _read(path, root))
    if sum(len(value.raw) for value in sources.values()) > 32 * 1024 * 1024:
        raise ValueError("LaTeX project exceeds 32 MiB source limit")
    visit = len(events)
    events.append((source, None, visit))
    for command in commands(visible_text(source.text)):
        events.append((source, command, visit))
        if command.name in {"input", "include"}:
            child = _literal_path(command.value, path.parent, root, ".tex")
            _walk(child, root, sources, events, bibs, active | {path})
        elif command.name in {"bibliography", "addbibresource"}:
            bibs.extend(
                _literal_path(value, path.parent, root, ".bib")
                for value in command.value.split(",")
            )


def _bibliography(paths, root, sources):
    entries = {}
    for path in dict.fromkeys(paths):
        source = _read(path, root, "bibtex")
        sources[path.resolve()] = source
        for key, entry in parse_string(source.text, source_name=source.file).entries.items():
            if key in entries:
                raise ValueError(f"Duplicate bibliography key: {key}")
            entries[key] = entry
    if not paths:
        raise ValueError("LaTeX claim extraction requires a bibliography (--bib)")
    return entries


def extract(request: Request) -> Extraction:
    path = request.path.resolve()
    root = (request.project_root or path.parent).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Entry file must be within the project root")
    sources, events, discovered = {}, [], []
    _walk(path, root, sources, events, discovered, set())
    bibs = [p.resolve() for p in request.bibliographies] or discovered
    entries = _bibliography(bibs, root, sources)
    extraction = Extraction(
        {
            "kind": "latex",
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(sources[path].raw),
        },
        list(sources.values()),
        {key: [] for key in entries},
        references={key: asdict(entry) for key, entry in entries.items()},
        extractor={"id": "latex", "version": "1", "strategy": "references"},
    )
    return extraction
