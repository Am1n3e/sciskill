"""PDF fidelity checks operate on original manuscript text, independently of support."""

import json
from pathlib import Path

import pytest
import yaml
from reportlab.pdfgen.canvas import Canvas
from test_claims import assert_public_contract

from bib_lint.claims.workflow import run_claims


def pdf_workspace(tmp_path):
    path = tmp_path / "paper.PDF"
    pdf = Canvas(str(path))
    pdf.drawString(50, 700, "Background.")
    pdf.showPage()
    pdf.drawString(50, 700, "Method X improves accuracy")
    pdf.showPage()
    pdf.drawString(50, 700, "[1].")
    pdf.drawString(50, 650, "References")
    pdf.drawString(50, 620, "[1] Jane Smith. Example Research. Example Journal, 2024.")
    pdf.save()
    seeded = run_claims(path, output=tmp_path / "claims")
    return path, Path(seeded["report_path"])


def fill_pdf(path, page=2, text="Method X improves accuracy\n[1]."):
    data = yaml.safe_load(path.read_text())
    data["citations"][0]["claims"] = [
        {
            "claim_id": "claim-0001",
            "claim": text,
            "location": {"page": page},
            "validation": {"result": "unresolved", "details": "Awaiting cited PDF comparison."},
        }
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return data


def test_pdf_seeds_same_bib_lint_references_with_empty_claims(tmp_path):
    from bib_lint.pdf_input import extract_pdf

    original, report = pdf_workspace(tmp_path)
    data = yaml.safe_load(report.read_text())
    assert_public_contract(data, "pdf")
    expected = extract_pdf(original)
    assert [c["citation_key"] for c in data["citations"]] == [
        i["entry"]["key"] for i in expected["items"]
    ]
    assert data["citations"][0]["claims"] == []
    private = yaml.safe_load((report.parent / ".provenance/provenance.yaml").read_text())
    assert private["references"]["pdf-ref-0001"]["fields"]["title"] == "Example Research"


def test_pdf_verbatim_quote_can_cross_pages_but_public_location_is_start_page(tmp_path):
    original, report = pdf_workspace(tmp_path)
    before = original.read_bytes()
    data = fill_pdf(report)
    result = run_claims(report)
    assert result["complete"] and result["summary"]["unique_claims"] == 1
    assert yaml.safe_load(report.read_text()) == data
    assert_public_contract(data, "pdf")
    check = json.loads((report.parent / ".provenance/check.json").read_text())
    assert {r["page"] for r in check["claims"][0]["location"]["pdf_regions"]} == {2, 3}
    assert "page 2" in (report.parent / "summary.md").read_text()
    assert original.read_bytes() == before


@pytest.mark.parametrize(
    "page,text",
    [
        (1, "Method X improves accuracy\n[1]."),
        (True, "Method X improves accuracy"),
        (2, "Method X improves performance"),
        (2, "Method X improves accuracy [1]."),
    ],
)
def test_pdf_wrong_page_paraphrase_and_normalized_quote_fail(tmp_path, page, text):
    _, report = pdf_workspace(tmp_path)
    fill_pdf(report, page, text)
    before = report.read_bytes()
    with pytest.raises(ValueError):
        run_claims(report)
    assert report.read_bytes() == before


def test_pdf_locations_cannot_add_extraction_coordinates(tmp_path):
    _, report = pdf_workspace(tmp_path)
    data = fill_pdf(report)
    data["citations"][0]["claims"][0]["location"]["line"] = 2
    report.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="exactly"):
        run_claims(report)


def test_source_sha_and_changed_pdf_are_checked(tmp_path):
    original, report = pdf_workspace(tmp_path)
    data = fill_pdf(report)
    data["document"]["sha256"] = "0" * 64
    report.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="original manuscript"):
        run_claims(report)
    fill_pdf(report)
    original.write_bytes(b"broken PDF")
    with pytest.raises(ValueError):
        run_claims(report)
