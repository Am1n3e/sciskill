"""Local citation-containing sentence extraction, with explicit review coverage."""

import re
from pathlib import Path

from bib_lint.citation_keys import resolve_citation_key
from bib_lint.claims.extractors.tex_syntax import Command, commands, visible_text
from bib_lint.claims.protocols import CitationOccurrence, Claim, Extraction, Request, Source
from bib_lint.claims.text import diagnostic, digest, location, sentence_span
from bib_lint.parser import parse_string

CITATIONS = {
    "cite",
    "citet",
    "citep",
    "citealt",
    "citealp",
    "citeauthor",
    "citeyear",
    "citeyearpar",
    "autocite",
    "parencite",
    "textcite",
}
STRUCTURAL = re.compile(
    r"\\(?:begin|end|section|subsection|subsubsection|paragraph|label|input|include|nocite)"
    r"\*?\s*\{[^{}]*\}|(?m:^\\(?:textbf|emph)\{[^{}\n]*[.!?]\}[ \t]*\r?$)"
)


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


def _claim_text(source: Source, command: Command):
    visible = visible_text(source.text)
    marker = re.search(r"\\begin\{document\}", visible)
    if marker:
        visible = " " * marker.end() + visible[marker.end() :]
    visible = STRUCTURAL.sub(
        lambda m: "".join(c if c in "\r\n" else " " for c in m.group()), visible
    )
    left, right = sentence_span(visible, command.start, command.end)
    remaining = visible[left : command.start] + visible[command.end : right]
    if len(re.findall(r"[a-zA-Z]{2,}", remaining)) < 2:
        return None
    return left, right


def _keys(command, entries, extraction, where):
    keys = []
    for raw in dict.fromkeys(k.strip() for k in command.value.split(",") if k.strip()):
        try:
            key = resolve_citation_key(raw, entries)
        except ValueError:
            key = None
        if key is None:
            extraction.diagnostics.append(diagnostic("unresolved_citation", raw, where))
        else:
            extraction.citations.setdefault(key, [])
            keys.append(key)
    return keys


def _citations(events, entries, extraction):
    spans = {}
    for source, command, visit in events:
        if command is None or command.name in {
            "input",
            "include",
            "bibliography",
            "addbibresource",
            "nocite",
        }:
            continue
        where = location(source, command.start, command.end)
        extraction.counts["citation_occurrences"] += 1
        if command.name not in CITATIONS or not command.value:
            extraction.diagnostics.append(diagnostic("unsupported_citation", command.name, where))
            continue
        keys = _keys(command, entries, extraction, where)
        extraction.occurrences.append(
            CitationOccurrence(
                f"citation-{len(extraction.occurrences) + 1:04d}",
                source.text[command.start : command.end],
                where,
                tuple(keys),
                visit,
            )
        )
        span = _claim_text(source, command)
        if span is None:
            extraction.counts["no_claim_citations"] += 1
            extraction.diagnostics.append(
                diagnostic("no_claim", "No associated prose found", where)
            )
        elif keys:
            left, right = span
            identity = (visit, left, right)
            if identity not in spans:
                spans[identity] = Claim(
                    f"claim-{len(spans) + 1:04d}",
                    source.text[left:right],
                    location(source, left, right),
                )
            for key in keys:
                if spans[identity] not in extraction.citations[key]:
                    extraction.citations[key].append(spans[identity])


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
        {},
        counts={"citation_occurrences": 0, "no_claim_citations": 0},
        extractor={"id": "latex", "version": "1", "strategy": "sentences"},
    )
    _citations(events, entries, extraction)
    if extraction.counts["citation_occurrences"]:
        extraction.diagnostics.insert(
            0,
            diagnostic(
                "sentence_baseline",
                "Local sentence spans require review of claim boundaries and attribution",
            ),
        )
    return extraction
