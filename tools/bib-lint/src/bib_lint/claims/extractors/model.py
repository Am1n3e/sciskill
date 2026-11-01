"""Semantic extraction over local source/citation evidence; never validates support."""

from collections import defaultdict

from bib_lint.claims.extractors import codex, latex, pdf
from bib_lint.claims.protocols import Claim, Extraction, Location, Request
from bib_lint.claims.text import diagnostic, location, offset


def _document(extraction):
    return {
        "sources": [
            {"file": source.file, "text": source.text}
            for source in extraction.sources
            if source.metadata.get("kind") != "bibtex"
        ],
        "citations": [
            {
                "citation_id": occurrence.citation_id,
                "text": occurrence.text,
                "location": occurrence.location.to_dict(),
                "keys": list(occurrence.keys),
            }
            for occurrence in extraction.occurrences
        ],
    }


def _find_span(source, text, occurrence):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Model claim must contain nonempty verbatim text")
    anchor = offset(source.text, occurrence.location.start)
    matches, cursor = [], 0
    while (start := source.text.find(text, cursor)) >= 0:
        distance = max(start - anchor, anchor - (start + len(text)), 0)
        matches.append((distance, start))
        cursor = start + 1
    matches.sort()
    if not matches or (len(matches) > 1 and matches[0][0] == matches[1][0]):
        raise ValueError(f"Model claim cannot be anchored uniquely in {source.file}")
    start = matches[0][1]
    return start, start + len(text)


def _location(source, start, end):
    span = location(source, start, end)
    if source.metadata.get("kind") != "pdf":
        return span
    regions, cursor = [], 0
    for line in source.metadata["regions"]:
        stop = cursor + len(line["text"])
        if cursor < end and stop > start:
            regions.append({k: line[k] for k in ("page", "x0", "top", "x1", "bottom")})
        cursor = stop + 1
    return Location(span.start, span.end, tuple(regions))


def _items(response, occurrences):
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        raise ValueError("Model response requires citation items")
    items = {}
    for item in response["items"]:
        if not isinstance(item, dict) or item.get("citation_id") not in occurrences:
            raise ValueError("Model returned an unknown citation occurrence")
        key = item["citation_id"]
        if key in items:
            raise ValueError("Model returned a duplicate citation occurrence")
        _validate_item(item)
        items[key] = item
    if set(items) != set(occurrences):
        raise ValueError("Model omitted citation occurrences")
    return items


def _validate_item(item):
    disposition = item.get("disposition")
    if disposition not in {"claims_extracted", "no_claim", "needs_review"}:
        raise ValueError("Model citation disposition is invalid")
    if not isinstance(item.get("claims"), list) or not isinstance(item.get("details"), str):
        raise ValueError("Model citation requires claims and details")
    if disposition == "claims_extracted" and not item["claims"]:
        raise ValueError("Extracted citation must contain claims")
    if disposition != "claims_extracted" and not item["details"].strip():
        raise ValueError("Unextracted citation requires an explanation")
    if disposition == "no_claim" and item["claims"]:
        raise ValueError("no_claim citation cannot contain claims")


def _apply(extraction, response):
    occurrences = {o.citation_id: o for o in extraction.occurrences}
    items = _items(response, occurrences)
    sources = {s.file: s for s in extraction.sources}
    records, pending = {}, []
    extraction.citations = {key: [] for key in extraction.citations}
    extraction.diagnostics = [
        d for d in extraction.diagnostics if d["code"] not in {"sentence_baseline", "no_claim"}
    ]
    extraction.counts["no_claim_citations"] = 0
    for rank, occurrence in enumerate(extraction.occurrences):
        item = items[occurrence.citation_id]
        _disposition(extraction, item, occurrence)
        for proposed in item["claims"]:
            _propose(proposed, occurrence, sources, records, pending, rank)
    _attach(extraction, records, pending)
    diagnostics = response.get("diagnostics")
    if not isinstance(diagnostics, list):
        raise ValueError("Model response requires diagnostics")
    for value in diagnostics:
        if not isinstance(value, dict) or not all(
            isinstance(value.get(k), str) and value[k].strip() for k in ("code", "message")
        ):
            raise ValueError("Model diagnostic requires code and message")
        extraction.diagnostics.append({"code": value["code"], "message": value["message"]})


def _disposition(extraction, item, occurrence):
    disposition = item["disposition"]
    if not occurrence.keys and item["claims"]:
        raise ValueError("Model cannot assign claims to unresolved citation keys")
    if disposition != "claims_extracted":
        extraction.diagnostics.append(diagnostic(disposition, item["details"], occurrence.location))
    if disposition == "no_claim":
        extraction.counts["no_claim_citations"] += 1


def _propose(proposed, occurrence, sources, records, pending, rank):
    if not isinstance(proposed, dict) or proposed.get("file") != occurrence.location.start.file:
        raise ValueError("Model claim must reference the citation's captured source file")
    source = sources[proposed["file"]]
    start, end = _find_span(source, proposed.get("claim"), occurrence)
    # Distinguish repeated document appearances of the same physical include.
    identity = (occurrence.document_occurrence, source.file, start, end)
    records.setdefault(identity, (source, proposed["claim"], _location(source, start, end), rank))
    pending.append((identity, occurrence.keys))


def _attach(extraction, records, pending):
    ordered = sorted(records, key=lambda k: (records[k][3], k[2], k[3]))
    claims = {}
    for index, key in enumerate(ordered, 1):
        _, text, where, _ = records[key]
        claims[key] = Claim(f"claim-{index:04d}", text, where)
    links = defaultdict(set)
    for identity, keys in pending:
        for key in keys:
            links[key].add(identity)
    for key in extraction.citations:
        extraction.citations[key] = [claims[i] for i in ordered if i in links[key]]


def extract(request: Request) -> Extraction:
    reader = latex if request.path.suffix.lower() == ".tex" else pdf
    extraction = reader.extract(request)
    selected_model = request.model
    if extraction.occurrences:
        selected_model = selected_model or codex.configured_model()
        response = codex.complete(_document(extraction), selected_model)
        _apply(extraction, response)
    extraction.extractor = {
        "id": "model",
        "backend": "codex",
        "version": "1",
        "prompt_version": "1",
        "model": selected_model or "codex-default",
    }
    return extraction
