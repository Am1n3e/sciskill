"""Seed PDF references and retain manuscript text with the bib-lint PDF extractor."""

from bib_lint.claims.protocols import (
    Extraction,
    Request,
    Source,
)
from bib_lint.claims.text import digest
from bib_lint.pdf_input import DEFAULT_LIMITS, extract_pdf


def _text(lines):
    fragments, offsets, cursor = [], [], 0
    for line in lines:
        value = line["text"] + "\n"
        offsets.append((cursor, cursor + len(line["text"]), line))
        fragments.append(value)
        cursor += len(value)
    return "".join(fragments), offsets


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
        {item["entry"]["key"]: [] for item in report["items"]},
        list(report["extraction"]["diagnostics"]),
        {},
        {"id": "pdf", "version": "1", "strategy": "references"},
    )
    extraction.references = {
        item["entry"]["key"]: {**item["entry"], "printed_label": item["pdf"]["label"]}
        for item in report["items"]
    }
    if report["claim_image_pages"]:
        extraction.diagnostics.append(
            {
                "code": "image_regions",
                "message": "Image-only claim content is not extracted",
                "pages": report["claim_image_pages"],
            }
        )
    return extraction
