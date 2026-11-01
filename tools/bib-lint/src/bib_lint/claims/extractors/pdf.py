"""PDF citation sentence spans from the existing bounded text/geometry worker."""

import re

from bib_lint.claims.protocols import (
    CitationOccurrence,
    Claim,
    Extraction,
    Location,
    Request,
    Source,
)
from bib_lint.claims.text import diagnostic, digest, location, sentence_span
from bib_lint.pdf_input import DEFAULT_LIMITS, extract_pdf

NUMERIC = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")


def _numeric_keys(value, labels):
    keys = []
    for part in value.split(","):
        endpoints = re.split(r"[-–]", part.strip())
        first, last = int(endpoints[0]), int(endpoints[-1])
        if not 0 <= last - first < 3000:
            return []
        for number in range(first, last + 1):
            matches = labels.get(str(number), [])
            if len(matches) != 1:
                return []
            keys.extend(matches)
    return list(dict.fromkeys(keys))


def _author_patterns(items):
    patterns = {}
    for item in items:
        entry = item["entry"]
        authors = entry["persons"].get("author", [])
        year = entry["fields"].get("year", "")
        if not authors or not year:
            continue
        name = " ".join(authors[0]["last"])
        if not name:
            continue
        original = item["pdf"]["text"]
        match = re.search(re.escape(year) + r"([a-z]?)\b", original)
        suffix = match[1] if match else ""
        pattern = (
            r"\b"
            + re.escape(name)
            + r"(?:\s+(?:et\s+al\.?|and\s+[\w'-]+|&\s+[\w'-]+))?\s*"
            + r"[\[(]?\s*"
            + re.escape(year + suffix)
            + r"\s*[\])]?"
            + r"(?![a-z\d])"
        )
        patterns.setdefault(pattern, []).append(entry["key"])
    return patterns


def _mentions(text, items):
    labels = {}
    for item in items:
        labels.setdefault(item["pdf"]["label"], []).append(item["entry"]["key"])
    mentions = []
    for pattern, keys in _author_patterns(items).items():
        mentions.extend(
            (m.start(), m.end(), keys if len(keys) == 1 else []) for m in re.finditer(pattern, text)
        )
    for match in NUMERIC.finditer(text):
        if not any(a <= match.start() and match.end() <= b for a, b, _ in mentions):
            mentions.append((match.start(), match.end(), _numeric_keys(match[1], labels)))
    return sorted(mentions)


def _text(lines):
    fragments, offsets, cursor = [], [], 0
    for line in lines:
        value = line["text"] + "\n"
        offsets.append((cursor, cursor + len(line["text"]), line))
        fragments.append(value)
        cursor += len(value)
    return "".join(fragments), offsets


def _regions(offsets, start, end):
    return tuple(
        {k: line[k] for k in ("page", "x0", "top", "x1", "bottom")}
        for a, b, line in offsets
        if a < end and b > start
    )


def _claims(extraction, source, items, offsets):
    spans = {}
    mentions = _mentions(source.text, items)
    extraction.counts["citation_occurrences"] = len(mentions)
    for start, end, keys in mentions:
        where = location(source, start, end)
        extraction.occurrences.append(
            CitationOccurrence(
                f"citation-{len(extraction.occurrences) + 1:04d}",
                source.text[start:end],
                where,
                tuple(keys),
            )
        )
        if not keys:
            extraction.diagnostics.append(
                diagnostic("unresolved_citation", source.text[start:end], where)
            )
            continue
        left, right = sentence_span(source.text, start, end)
        if (left, right) not in spans:
            span = location(source, left, right)
            spans[left, right] = Claim(
                f"claim-{len(spans) + 1:04d}",
                source.text[left:right],
                Location(span.start, span.end, _regions(offsets, left, right)),
            )
        for key in keys:
            claims = extraction.citations.setdefault(key, [])
            if spans[left, right] not in claims:
                claims.append(spans[left, right])


def extract(request: Request) -> Extraction:
    if request.bibliographies or request.project_root:
        raise ValueError("--bib and --project-root apply only to LaTeX inputs")
    path = request.path.resolve()
    report = extract_pdf(path, include_body=True)
    raw = path.read_bytes()
    if digest(raw) != report["source"]["sha256"]:
        raise ValueError("PDF changed during extraction")
    text, offsets = _text(report["claim_body"])
    source = Source(
        path.name,
        path,
        raw,
        text,
        f"sources/{path.name}.txt",
        {
            "kind": "pdf",
            "page_sizes": report["extraction"]["document"]["page_sizes"],
            "settings": DEFAULT_LIMITS,
            "extractor": report["extraction"]["extractor"],
            "regions": [line for _, _, line in offsets],
        },
    )
    extraction = Extraction(
        {"kind": "pdf", "path": path.name, "sha256": digest(raw)},
        [source],
        {},
        list(report["extraction"]["diagnostics"]),
        {"no_claim_citations": 0},
        {"id": "pdf", "version": "1", "strategy": "sentences"},
    )
    _claims(extraction, source, report["items"], offsets)
    extraction.diagnostics.append(
        diagnostic(
            "sentence_baseline",
            "Local PDF sentence spans and citation mappings require semantic review",
        )
    )
    if report["claim_image_pages"]:
        extraction.diagnostics.append(
            {
                "code": "image_regions",
                "message": "Image-only claim content is not extracted",
                "pages": report["claim_image_pages"],
            }
        )
    return extraction
