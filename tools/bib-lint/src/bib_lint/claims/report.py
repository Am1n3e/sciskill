"""The public claim-report contract; internal extraction records stay private."""

from importlib.metadata import PackageNotFoundError, version

from bib_lint.claims.protocols import Extraction, Location, Position


def producer_version() -> str:
    try:
        return version("sciskill")
    except PackageNotFoundError:
        return version("bib-lint")


def header(document: dict, mode: str) -> dict:
    if document.get("kind") not in {"pdf", "latex"}:
        raise ValueError("Claim document kind must be pdf or latex")
    return {
        "schema_version": 1,
        "scikill_version": producer_version(),
        "document": {key: document[key] for key in ("kind", "path", "sha256")},
        "setup": {"validation_mode": mode},
        "citations": [],
    }


def public_location(where: Location, kind: str, sources: dict) -> dict:
    if kind == "pdf":
        if where.pdf_regions:
            return {"page": where.pdf_regions[0]["page"]}
        rows = sources[where.start.file].metadata["regions"]
        return {"page": rows[where.start.line - 1]["page"]}
    return {
        "file": where.start.file,
        "start": {"line": where.start.line, "column": where.start.column},
        "end": {"line": where.end.line, "column": where.end.column},
    }


def public_extraction(extraction: Extraction) -> dict:
    sources = {source.file: source for source in extraction.sources}
    diagnostics = []
    for original in extraction.diagnostics:
        item = {key: original[key] for key in ("code", "message")}
        where = original.get("location")
        if where:
            location = Location(Position(**where["start"]), Position(**where["end"]))
            item["location"] = public_location(location, extraction.document["kind"], sources)
        elif "page" in original:
            item["location"] = {"page": original["page"]}
        if "pages" in original:
            item["pages"] = original["pages"]
        diagnostics.append(item)
    return {
        "state": "needs_review" if diagnostics else "complete",
        "diagnostics": diagnostics,
    }


def location_label(where: dict) -> str:
    if "page" in where:
        return f"page {where['page']}"
    point = where["start"]
    return f"{where['file']}:{point['line']}:{point['column']}"


def finding_label(finding: dict) -> str:
    label = f"{finding['code']}: {finding['message']}"
    if "location" in finding:
        label += f" ({location_label(finding['location'])})"
    if "pages" in finding:
        label += " (pages " + ", ".join(map(str, finding["pages"])) + ")"
    return label
