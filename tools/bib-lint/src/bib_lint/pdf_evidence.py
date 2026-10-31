"""Validate inline PDF provenance and bind it to input/workspace identity."""

import copy
import hashlib
import json
import math
import re


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _payload(report):
    extraction = {k: v for k, v in report["extraction"].items() if k != "evidence_sha256"}
    return {
        "extraction": extraction,
        "items": [
            {"entry": i["entry"], "pdf": i["pdf"], "extraction": i["validations"]["extraction"]}
            for i in report["items"]
        ],
    }


def seal_extraction(report):
    """Seal once at extraction; verification outcomes do not alter this checksum."""
    report["extraction"]["evidence_sha256"] = _hash(_payload(report))
    return report


def saved_identity(report):
    extraction = report["extraction"]
    return {
        "document_sha256": extraction["document"]["sha256"],
        **{k: extraction[k] for k in ("extractor", "parser", "settings")},
    }


def fingerprint_evidence(report):
    payload = copy.deepcopy(_payload(report))
    payload["extraction"]["document"].pop("name", None)
    return payload


def _text(value, name, *, empty=False):
    if not isinstance(value, str) or (not empty and not value):
        raise ValueError(f"PDF {name} must be text")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _page(value, count):
    if type(value) is not int or not 1 <= value <= count:
        raise ValueError("PDF evidence page must be a physical page number")


def _box(fragment, sizes):
    if not isinstance(fragment, dict):
        raise ValueError("PDF evidence box must be an object")
    _page(fragment.get("page"), len(sizes))
    coordinates = [fragment.get(k) for k in ("x0", "top", "x1", "bottom")]
    if not all(_number(v) for v in coordinates):
        raise ValueError("PDF evidence box must contain finite numbers")
    x0, top, x1, bottom = coordinates
    size = sizes[fragment["page"] - 1]
    if not (0 <= x0 <= x1 <= size["width"] and 0 <= top <= bottom <= size["height"]):
        raise ValueError("PDF evidence box must fit inside its physical page")


def _diagnostics(diagnostics, pages, *, item=False):
    if not isinstance(diagnostics, list):
        raise ValueError("PDF diagnostics must be a list")
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            raise ValueError("PDF diagnostic must be an object")
        _text(diagnostic.get("code"), "diagnostic code")
        _text(diagnostic.get("message"), "diagnostic message")
        if diagnostic.get("result", "unknown") not in ("unknown", "mismatch"):
            raise ValueError("PDF diagnostic result must be unknown or mismatch")
        if "page" in diagnostic:
            _page(diagnostic["page"], pages)
        if item and (
            not isinstance(diagnostic.get("fields"), list)
            or any(not isinstance(v, str) for v in diagnostic["fields"])
        ):
            raise ValueError("PDF diagnostic fields must be a list of text")


def _document(extraction):
    document = extraction.get("document")
    if not isinstance(document, dict):
        raise ValueError("PDF extraction requires a document")
    _text(document.get("name"), "document name")
    if not isinstance(document.get("sha256"), str) or not re.fullmatch(
        "[a-f0-9]{64}", document["sha256"]
    ):
        raise ValueError("PDF document requires a SHA-256 checksum")
    count, sizes = document.get("pages"), document.get("page_sizes")
    if type(count) is not int or count < 1 or not isinstance(sizes, list) or len(sizes) != count:
        raise ValueError("PDF document requires physical page sizes")
    for size in sizes:
        if not isinstance(size, dict) or any(
            not _number(size.get(k)) or size[k] <= 0 for k in ("width", "height")
        ):
            raise ValueError("PDF page sizes must be finite positive dimensions")
    return sizes


def _identity(extraction):
    for component in ("extractor", "parser"):
        value = extraction.get(component)
        if not isinstance(value, dict):
            raise ValueError(f"PDF extraction requires {component} identity")
        for key in ("id", "version"):
            _text(value.get(key), component + " " + key)
    settings = extraction.get("settings")
    if not isinstance(settings, dict) or any(
        not isinstance(k, str) or not _number(v) or v <= 0 for k, v in settings.items()
    ):
        raise ValueError("PDF extraction settings must contain positive numeric limits")


def _mapping(mapping, fragments, uris):
    if not isinstance(mapping, dict):
        raise ValueError("PDF field mapping must be an object")
    if "uri" in mapping:
        index = mapping["uri"]
        if type(index) is not int or not 0 <= index < len(uris):
            raise ValueError("PDF URI field mapping is outside the evidence")
        return
    index, start, end = (mapping.get(k) for k in ("fragment", "start", "end"))
    if (
        any(type(v) is not int for v in (index, start, end))
        or not 0 <= index < len(fragments)
        or not 0 <= start < end <= len(fragments[index]["text"])
    ):
        raise ValueError("PDF field mapping must select original fragment text")


def _fields(item, pdf):
    evidence = pdf.get("field_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("PDF field mappings must be an object")
    for field, mappings in evidence.items():
        _text(field, "field mapping name")
        if not isinstance(mappings, list) or not mappings:
            raise ValueError("PDF field mapping must contain evidence spans")
        for mapping in mappings:
            _mapping(mapping, pdf["fragments"], pdf["uris"])
    aliases = {
        "journal": "venue",
        "booktitle": "venue",
        "eprint": "arxiv",
        "archiveprefix": "arxiv",
    }
    for field in item["entry"]["fields"]:
        if field not in evidence and aliases.get(field) not in evidence:
            raise ValueError(f"PDF field mapping missing for {field}")
    if item["entry"]["persons"].get("author") and "authors" not in evidence:
        raise ValueError("PDF field mapping missing for authors")


def _reference(item, sizes):
    pdf = item.get("pdf")
    if not isinstance(pdf, dict):
        raise ValueError("PDF reference requires original evidence")
    if pdf.get("label") is not None:
        _text(pdf["label"], "printed label")
    _text(pdf.get("text"), "reference text")
    fragments, uris = pdf.get("fragments"), pdf.get("uris")
    if not isinstance(fragments, list) or not fragments or not isinstance(uris, list):
        raise ValueError("PDF reference requires original fragments and URI evidence")
    for fragment in fragments:
        _box(fragment, sizes)
        _text(fragment.get("text"), "original fragment")
    for uri in uris:
        _box(uri, sizes)
        _text(uri.get("uri"), "URI target")
    _diagnostics(pdf.get("diagnostics"), len(sizes), item=True)
    validation = item["validations"].get("extraction")
    if (
        not isinstance(validation, dict)
        or validation.get("state") not in ("complete", "needs_review")
        or validation.get("diagnostics") != pdf["diagnostics"]
    ):
        raise ValueError("PDF reference extraction state must retain its diagnostics")
    if pdf["diagnostics"] and validation["state"] == "complete":
        raise ValueError("PDF reference with diagnostics needs review")
    _fields(item, pdf)


def validate_pdf_report(report):
    extraction = report.get("extraction")
    if (
        not isinstance(extraction, dict)
        or type(extraction.get("schema_version")) is not int
        or extraction["schema_version"] != 1
    ):
        raise ValueError("Schema 4 requires versioned PDF extraction evidence")
    _validate_seal(report)
    if report.get("verification_scope", {}).get("mode") != "all":
        raise ValueError("PDF citation usage must remain unknown; scope must be all")
    if not report["items"]:
        raise ValueError("PDF extraction must contain references")
    sizes = _document(extraction)
    _identity(extraction)
    _coverage(extraction, sizes)
    for item in report["items"]:
        _reference(item, sizes)
        if any(f["page"] not in extraction["reference_pages"] for f in item["pdf"]["fragments"]):
            raise ValueError("PDF reference fragment page is outside reference-page coverage")


def _coverage(extraction, sizes):
    if extraction.get("state") not in ("complete", "needs_review"):
        raise ValueError("PDF extraction state must be complete or needs_review")
    count = extraction.get("unresolved_fragments")
    if type(count) is not int or count < 0:
        raise ValueError("PDF unresolved fragment count must be a nonnegative integer")
    pages = extraction.get("reference_pages")
    if (
        not isinstance(pages, list)
        or not pages
        or any(type(p) is not int for p in pages)
        or pages != sorted(set(pages))
    ):
        raise ValueError("PDF reference pages must be an ordered unique list")
    for page in pages:
        _page(page, len(sizes))
    _diagnostics(extraction.get("diagnostics"), len(sizes))
    if extraction["state"] == "complete" and (count or extraction["diagnostics"]):
        raise ValueError("PDF document with unresolved coverage needs review")


def _validate_seal(report):
    try:
        actual = _hash(_payload(report))
    except (KeyError, TypeError) as exc:
        raise ValueError("PDF extraction evidence is missing or malformed") from exc
    if report["extraction"].get("evidence_sha256") != actual:
        raise ValueError("PDF evidence checksum mismatch")


def extraction_summary(report):
    extraction = report.get("extraction")
    if extraction is None:
        return None
    return {
        "state": extraction["state"],
        "occurrence_count": len(report["items"]),
        **{k: extraction[k] for k in ("unresolved_fragments", "reference_pages", "diagnostics")},
    }


def apply_extraction(result, item):
    """Recompute decisions after excluding comparisons of uncertain input fields."""
    from bib_lint.verification.consensus import CHECKED_FIELDS, build_consensus

    extraction = item["validations"].get("extraction")
    if not extraction or extraction["state"] == "complete":
        return result
    diagnostics = extraction["diagnostics"]
    aliases = {"journal": "venue", "booktitle": "venue", "eprint": "arxiv", "author": "authors"}
    affected = set()
    findings = list(result.get("input_findings", []))
    for diagnostic in diagnostics:
        fields = diagnostic["fields"]
        outcome = diagnostic.get("result", "unknown")
        if outcome == "unknown":
            affected.update(aliases.get(field, field) for field in (fields or CHECKED_FIELDS))
        findings.append(
            {
                "field": ", ".join(fields) or "reference",
                "code": diagnostic["code"],
                "message": diagnostic["message"],
                "result": outcome,
            }
        )
    methods = copy.deepcopy(result["methods"])
    for method in methods:
        for comparison in method.get("comparisons", []):
            if comparison["field"] in affected:
                comparison["result"] = "unknown"
        method["differences"] = [
            d for d in method.get("differences", []) if d["field"] not in affected
        ]
    rebuilt = build_consensus(methods, input_findings=findings)
    if "complete" in result:
        rebuilt["complete"] = result["complete"]
    if rebuilt["is_correct"] is True:
        rebuilt["is_correct"] = None
    return rebuilt
