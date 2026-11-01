"""Check skill-authored claims against a freshly read original manuscript."""

from pathlib import Path

from bib_lint.claims.extractors import latex, pdf
from bib_lint.claims.protocols import Claim, Location, Position, Request, Validation
from bib_lint.claims.text import digest, location, offset
from bib_lint.claims.yaml_io import fields, read_yaml


def _evidence(path):
    root = path.parent.resolve()
    directory = root / ".provenance"
    if directory.is_symlink():
        raise ValueError("Private evidence must not be a symlink")
    saved = read_yaml(directory / "provenance.yaml")
    if not isinstance(saved, dict) or not isinstance(saved.get("input"), dict):
        raise ValueError("Original input context is missing; seed from the manuscript first")
    inputs = saved["input"]
    fields(inputs, ("path", "bibliographies", "project_root"), "Original input context")
    if not isinstance(inputs["path"], str) or not isinstance(inputs["bibliographies"], list):
        raise ValueError("Invalid original manuscript paths")
    if any(not isinstance(p, str) for p in inputs["bibliographies"]):
        raise ValueError("Original bibliography paths must be strings")
    if inputs["project_root"] is not None and not isinstance(inputs["project_root"], str):
        raise ValueError("Invalid original project root")
    request = Request(
        Path(inputs["path"]),
        tuple(Path(p) for p in inputs["bibliographies"]),
        Path(inputs["project_root"]) if inputs["project_root"] else None,
    )
    reader = latex if request.path.suffix.lower() == ".tex" else pdf
    extraction = reader.extract(request)
    old = {s["file"]: s["sha256"] for s in saved["sources"]}
    current = {s.file: digest(s.raw) for s in extraction.sources}
    if old != current:
        raise ValueError("Manuscript inputs changed; seed a new workspace")
    extraction.input = inputs
    return extraction


def _pdf_location(source, text, value):
    fields(value, ("page",), "PDF location")
    page = value["page"]
    if type(page) is not int or page < 1:
        raise ValueError("PDF location.page must be a positive physical page number")
    cursor = 0
    while (start := source.text.find(text, cursor)) >= 0:
        where = location(source, start, start + len(text))
        rows = source.metadata["regions"]
        if rows[where.start.line - 1]["page"] == page:
            selected, position = [], 0
            for row in rows:
                end = position + len(row["text"])
                if position < start + len(text) and end > start:
                    selected.append({k: row[k] for k in ("page", "x0", "top", "x1", "bottom")})
                position = end + 1
            return Location(where.start, where.end, tuple(selected))
        cursor = start + 1
    raise ValueError("Claim is not verbatim text starting on the stated PDF page")


def _latex_location(sources, text, value):
    fields(value, ("file", "start", "end"), "LaTeX location")
    file = value["file"]
    if (
        not isinstance(file, str)
        or file not in sources
        or sources[file].metadata["kind"] != "latex"
    ):
        raise ValueError("LaTeX claim must reference a manuscript source file")
    points = []
    for name in ("start", "end"):
        fields(value[name], ("line", "column"), "LaTeX endpoint")
        points.append(Position(file, value[name]["line"], value[name]["column"]))
    source = sources[file]
    start, end = (offset(source.text, p) for p in points)
    if source.text[start:end] != text:
        raise ValueError("Claim text does not match its LaTeX source location")
    return Location(*points)


def _claim(value, extraction, sources):
    fields(value, ("claim_id", "claim", "location", "validation"), "Claim")
    if not isinstance(value["claim_id"], str) or not value["claim_id"]:
        raise ValueError("Claim requires a nonempty claim_id")
    text = value["claim"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Claim requires nonempty verbatim text")
    fields(value["validation"], ("result", "details"), "Claim validation")
    assessment = Validation(**value["validation"])
    assessment.to_dict()
    if extraction.document["kind"] == "pdf":
        where = _pdf_location(extraction.sources[0], text, value["location"])
    else:
        where = _latex_location(sources, text, value["location"])
    return Claim(value["claim_id"], text, where, assessment)


def _report(path):
    data = read_yaml(path)
    fields(data, ("schema_version", "scikill_version", "document", "setup", "citations"), "Report")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported claim schema version")
    if not isinstance(data["scikill_version"], str) or not data["scikill_version"].strip():
        raise ValueError("Report requires scikill_version")
    fields(data["document"], ("kind", "path", "sha256"), "Document")
    fields(data["setup"], ("validation_mode",), "Setup")
    if not isinstance(data["setup"]["validation_mode"], str):
        raise ValueError("validation_mode must be a validator name")
    if not isinstance(data["citations"], list):
        raise ValueError("Report citations must be a list")
    return data


def extract(request: Request):
    if request.bibliographies or request.project_root:
        raise ValueError("--bib and --project-root apply only when seeding a manuscript")
    data = _report(request.path)
    extraction = _evidence(request.path)
    if data["document"] != extraction.document:
        raise ValueError("Report document does not match the original manuscript")
    sources, citations = {s.file: s for s in extraction.sources}, {}
    for item in data["citations"]:
        fields(item, ("citation_key", "claims"), "Citation")
        key = item["citation_key"]
        if not isinstance(key, str) or key not in extraction.references or key in citations:
            raise ValueError("Unknown or duplicate citation_key")
        if not isinstance(item["claims"], list):
            raise ValueError("Citation claims must be a list")
        citations[key] = [_claim(c, extraction, sources) for c in item["claims"]]
    if set(citations) != set(extraction.references):
        raise ValueError("Report must retain every extracted reference, including empty claims")
    extraction.citations = citations
    extraction.validation_mode = data["setup"]["validation_mode"]
    extraction.extractor = {"id": "skill", "version": "1"}
    return extraction
