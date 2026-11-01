"""Compose extraction and validation, check source fidelity, publish one artifact set."""

import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import yaml

from bib_lint.claims import load_validator
from bib_lint.claims.protocols import Extraction, Extractor, Request, Source, Validator
from bib_lint.claims.report import (
    finding_label,
    header,
    location_label,
    public_extraction,
    public_location,
)
from bib_lint.claims.text import digest, offset
from bib_lint.storage import write_json


def _extractor(path: Path) -> Extractor:
    from bib_lint.claims.extractors import agent, latex, pdf

    if path.suffix.lower() == ".tex":
        return latex
    if path.suffix.lower() == ".pdf":
        return pdf
    if path.suffix.lower() in {".yaml", ".yml"}:
        return agent
    raise ValueError("Use a LaTeX/PDF manuscript to seed references or claims.yaml to check quotes")


def _regions(claim, source, start, end):
    sizes = source.metadata.get("page_sizes", [])
    if source.metadata.get("kind") == "pdf" and not claim.location.pdf_regions:
        raise ValueError("PDF claim requires original page regions")
    for region in claim.location.pdf_regions:
        page = region.get("page")
        if type(page) is not int or not 1 <= page <= len(sizes):
            raise ValueError("PDF claim page is outside the document")
        box = [region.get(k) for k in ("x0", "top", "x1", "bottom")]
        if not all(type(v) in (int, float) and math.isfinite(v) for v in box):
            raise ValueError("PDF claim region requires finite coordinates")
        x0, top, x1, bottom = box
        if not (
            0 <= x0 <= x1 <= sizes[page - 1]["width"]
            and 0 <= top <= bottom <= sizes[page - 1]["height"]
        ):
            raise ValueError("PDF claim region is outside its page")
    if source.metadata.get("kind") == "pdf":
        expected, cursor = [], 0
        for line in source.metadata["regions"]:
            stop = cursor + len(line["text"])
            if cursor < end and stop > start:
                expected.append({k: line[k] for k in ("page", "x0", "top", "x1", "bottom")})
            cursor = stop + 1
        if expected != list(claim.location.pdf_regions):
            raise ValueError("PDF claim regions do not match its text span")


def _validate_claim(claim, sources, identities):
    start, end = claim.location.start, claim.location.end
    if start.file != end.file or start.file not in sources:
        raise ValueError("Claim location must reference a captured source")
    source = sources[start.file]
    left, right = offset(source.text, start), offset(source.text, end)
    if not claim.claim_id or not claim.claim or not left < right:
        raise ValueError("Claim requires an ID and a nonempty source span")
    if source.text[left:right] != claim.claim:
        raise ValueError("Claim text does not match its source location")
    identity = (claim.claim, claim.location)
    if claim.claim_id in identities and identities[claim.claim_id] != identity:
        raise ValueError("Repeated claim ID refers to different source text or locations")
    identities[claim.claim_id] = identity
    _regions(claim, source, left, right)


def _source_record(source: Source) -> dict:
    path = Path(source.snapshot)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "sources":
        raise ValueError("Snapshot path must stay within workspace sources")
    if source.path.read_bytes() != source.raw:
        raise ValueError(f"Input changed during extraction: {source.file}")
    return {
        "file": source.file,
        "sha256": digest(source.raw),
        "text_snapshot": f".provenance/{source.snapshot}",
        "text_sha256": digest(source.text.encode("utf-8")),
        **source.metadata,
    }


def build_report(
    extraction: Extraction, validator: Validator, mode: str
) -> tuple[dict, dict, dict]:
    sources = {source.file: source for source in extraction.sources}
    if len(sources) != len(extraction.sources):
        raise ValueError("Duplicate source identities")
    report = header(extraction.document, mode)
    provenance = {
        "schema_version": 1,
        "input": extraction.input,
        "references": extraction.references,
        "sources": [_source_record(source) for source in extraction.sources],
        "extraction": {
            "state": "needs_review" if extraction.diagnostics else "complete",
            "extractor": extraction.extractor,
            "diagnostics": extraction.diagnostics,
        },
        "claims": [],
    }
    identities = {}
    for key, claims in extraction.citations.items():
        records = []
        seen = set()
        for claim in claims:
            _validate_claim(claim, sources, identities)
            if claim.claim_id in seen:
                raise ValueError("Duplicate claim occurrence within citation group")
            seen.add(claim.claim_id)
            if not any(item["claim_id"] == claim.claim_id for item in provenance["claims"]):
                provenance["claims"].append(
                    {
                        "claim_id": claim.claim_id,
                        "location": claim.location.to_dict(),
                    }
                )
            records.append(
                {
                    "claim_id": claim.claim_id,
                    "claim": claim.claim,
                    "location": public_location(
                        claim.location, extraction.document["kind"], sources
                    ),
                    "validation": validator.validate(claim, key).to_dict(),
                }
            )
        report["citations"].append({"citation_key": key, "claims": records})
    counts = {
        **extraction.counts,
        "unique_claims": len(identities),
        "claim_citation_pairs": sum(len(c["claims"]) for c in report["citations"]),
        "reference_keys": len(report["citations"]),
        "references_without_claims": sum(not c["claims"] for c in report["citations"]),
        **{
            result: sum(
                claim["validation"]["result"] == result
                for citation in report["citations"]
                for claim in citation["claims"]
            )
            for result in ("valid", "invalid", "unresolved")
        },
        "unresolved_citations": sum(
            d["code"] in {"unresolved_citation", "unsupported_citation"}
            for d in extraction.diagnostics
        ),
        "uncertain_candidates": sum(
            d["code"] in {"needs_review", "unresolved_citation", "unsupported_citation"}
            for d in extraction.diagnostics
        ),
        "coverage_diagnostics": sum(
            d["code"] not in {"needs_review", "no_claim", "unresolved_citation"}
            for d in extraction.diagnostics
        ),
    }
    return report, provenance, counts


def _summary(report, counts, extraction, *, checked=False, review_notes=False):
    lines = [
        f"Validation mode: {report['setup']['validation_mode']}",
        f"Automated source capture: {extraction['state']}",
        f"Manuscript quote check: {'passed' if checked else 'pending'}",
        "",
    ]
    if review_notes:
        lines.extend(["[Agent review notes](review-notes.md)", ""])
    lines.extend(f"- {key.replace('_', ' ')}: {value}" for key, value in counts.items())
    for citation in report["citations"]:
        lines.extend(["", f"## {citation['citation_key']}", ""])
        for claim in citation["claims"]:
            validation = claim["validation"]
            lines.extend(
                [
                    f"- {claim['claim_id']}: {validation['result']} "
                    f"({location_label(claim['location'])})",
                    f"  Claim: {claim['claim']}",
                    f"  Details: {validation['details']}",
                ]
            )
    if extraction["diagnostics"]:
        lines.extend(["", "## Extraction diagnostics", ""])
        lines.extend(f"- {finding_label(d)}" for d in extraction["diagnostics"])
    return "\n".join(lines) + "\n"


def publish(output: Path, report: dict, summary: str, sources: list[Source], provenance: dict):
    """Publish a new directory atomically; identical reruns reuse the sealed output."""
    contents = {
        "claims.yaml": yaml.safe_dump(report, allow_unicode=True, sort_keys=False).encode(),
        "summary.md": summary.encode(),
        ".provenance/provenance.yaml": yaml.safe_dump(
            provenance, allow_unicode=True, sort_keys=False
        ).encode(),
    }
    for source in sources:
        contents[f".provenance/{source.snapshot}"] = source.text.encode("utf-8")
        if source.metadata.get("kind") == "pdf":
            contents[f".provenance/sources/original-{source.path.name}"] = source.raw
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("Output must not use symlinked paths")
    if output.exists():
        if not output.is_dir() or any(
            not (output / name).is_file()
            or (output / name).is_symlink()
            or (output / name).read_bytes() != raw
            for name, raw in contents.items()
        ):
            raise ValueError("Output already exists with different content; choose a new --output")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".bib-claims-", dir=output.parent))
    try:
        for name, raw in contents.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _write_text(path, text):
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a symlink: {path.name}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _check_assessments(extraction, report):
    for item in report["citations"]:
        for claim, record in zip(
            extraction.citations[item["citation_key"]], item["claims"], strict=True
        ):
            if claim.assessment is None or claim.assessment.to_dict() != record["validation"]:
                raise ValueError("Claim validation fields do not match the selected validator mode")


def run_claims(
    path, *, bib=(), project_root=None, output=None, mode=None, extractor: Extractor | None = None
) -> dict:
    if mode is not None:
        load_validator(mode)
    path = Path(path).expanduser().absolute()
    if path.is_dir():
        path = path / "main.tex"
    checking = path.suffix.lower() in {".yaml", ".yml"}
    before = path.read_bytes() if checking else None
    if checking and output is not None:
        raise ValueError("Check claims.yaml in its existing workspace; omit --output")
    root = Path(project_root).expanduser().resolve() if project_root else None
    request = Request(path, tuple(Path(p).expanduser().resolve() for p in bib), root)
    extraction = (extractor or _extractor(path)).extract(request)
    selected_mode = mode or extraction.validation_mode or "agent"
    if checking and mode is not None and mode != extraction.validation_mode:
        raise ValueError("--mode must match setup.validation_mode when checking a report")
    if not checking:
        extraction.input = {
            "path": str(path.resolve()),
            "project_root": str(root) if root else None,
            "bibliographies": [str(p) for p in request.bibliographies],
        }
    report, provenance, counts = build_report(
        extraction, load_validator(selected_mode), selected_mode
    )
    extraction_summary = public_extraction(extraction)
    if checking:
        _check_assessments(extraction, report)
        if path.read_bytes() != before:
            raise ValueError("Report changed while its claims were being checked")
        destination = path.parent.resolve()
        _write_text(
            destination / "summary.md",
            _summary(
                report,
                counts,
                extraction_summary,
                checked=True,
                review_notes=(destination / "review-notes.md").is_file(),
            ),
        )
        write_json(
            destination / ".provenance/check.json",
            {
                "report_sha256": digest(before),
                "document_sha256": report["document"]["sha256"],
                "claims": provenance["claims"],
                "summary": counts,
            },
        )
        report_path = path.resolve()
    else:
        selected_output = (
            Path(output).expanduser().absolute() if output else default_output(path, root)
        )
        if selected_output.is_symlink():
            raise ValueError("Output directory must not be a symlink")
        destination = selected_output.parent.resolve() / selected_output.name
        publish(
            destination,
            report,
            _summary(report, counts, extraction_summary),
            extraction.sources,
            provenance,
        )
        report_path = destination / "claims.yaml"
    return {
        "schema_version": 1,
        "command": "check-claims",
        "status": "quotes_checked" if checking else "awaiting_agent",
        "output_dir": str(destination),
        "report_path": str(report_path),
        "summary_path": str(destination / "summary.md"),
        "setup": report["setup"],
        "extraction": extraction_summary,
        "summary": counts,
        "error": None,
    }


def default_output(path, root):
    for parent in (root or path.parent, *(root or path.parent).parents):
        if (parent / ".sciskill/config.yaml").is_file():
            return parent / ".sciskill/cache/bib-claims"
    return path.with_name(path.stem + ".bib-claims")


def emit_result(result, machine):
    if machine:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            f"Claim checks: {result['status']}; "
            f"validation mode: {result['setup']['validation_mode']}"
        )
        if result.get("report_path"):
            print(f"claims: {result['report_path']}")
        if result.get("summary"):
            print("; ".join(f"{k}: {v}" for k, v in result["summary"].items()))
