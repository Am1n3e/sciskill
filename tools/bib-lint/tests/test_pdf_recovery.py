"""Unreadable bibliography pages remain explicit and never become empty success."""

import pytest
from PIL import Image
from provider_support import fixture_registry
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from support import FakeClient

from bib_lint.audit import run_audit
from bib_lint.pdf_input import PDFExtractionError, extract_pdf
from bib_lint.scope import validate_report


def _references(output, *, heading=True, label=1):
    output.setFont("Times-Bold", 12)
    if heading:
        output.drawString(50, 700, "References")
    output.setFont("Times-Roman", 10)
    output.drawString(50, 670, f"[{label}] Jane Smith. An Example Paper. Journal, 2025.")


def _scan(output):
    image = Image.new("RGB", (600, 800), "white")
    # The actual image pixels are intentionally opaque to a text-only extractor.
    output.drawImage(ImageReader(image), 50, 50, width=500, height=650)


def test_encrypted_pdf_is_a_controlled_unsupported_input(tmp_path):
    source = tmp_path / "encrypted.pdf"
    output = canvas.Canvas(str(source), encrypt="password", invariant=1)
    _references(output)
    output.save()
    before = source.read_bytes()
    with pytest.raises(PDFExtractionError, match="(?i)encrypted"):
        extract_pdf(source)
    assert source.read_bytes() == before


def test_image_only_pdf_identifies_ocr_page_in_its_failure(tmp_path):
    source = tmp_path / "scanned.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    _scan(output)
    output.save()
    with pytest.raises(PDFExtractionError) as failure:
        extract_pdf(source)
    assert any(
        d["code"] == "unreadable_reference_page" and d.get("page") == 1
        for d in failure.value.diagnostics
    )


def test_image_page_between_readable_reference_pages_is_not_lost(tmp_path):
    source = tmp_path / "mixed.pdf"
    output = canvas.Canvas(str(source), invariant=1, pagesize=(612, 792))
    _references(output)
    output.showPage()
    _scan(output)
    output.showPage()
    _references(output, heading=False, label=2)
    output.save()
    report = extract_pdf(source)
    validate_report(report)
    assert len(report["items"]) == 2
    assert report["extraction"]["state"] == "needs_review"
    assert report["extraction"]["reference_pages"] == [1, 2, 3]
    assert any(
        d["code"] == "unreadable_reference_page" and d.get("page") == 2
        for d in report["extraction"]["diagnostics"]
    )


def test_scanned_figure_before_bibliography_does_not_reduce_reference_coverage(tmp_path):
    source = tmp_path / "figure.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    _scan(output)
    output.showPage()
    _references(output)
    output.save()
    report = extract_pdf(source)
    assert report["extraction"]["state"] == "complete"
    assert report["extraction"]["reference_pages"] == [2]


def test_scanned_appendix_after_explicit_end_is_outside_reference_coverage(tmp_path):
    source = tmp_path / "appendix.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    _references(output)
    output.setFont("Times-Bold", 12)
    output.drawString(50, 600, "A Appendix")
    output.showPage()
    _scan(output)
    output.save()
    report = extract_pdf(source)
    assert report["extraction"]["state"] == "complete"
    assert report["extraction"]["reference_pages"] == [1]


def test_multiple_bibliographies_preserve_occurrences_and_warn(tmp_path):
    source = tmp_path / "multiple.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    _references(output)
    output.showPage()
    _references(output, label=2)
    output.save()
    report = extract_pdf(source)
    assert len(report["items"]) == 2
    assert report["extraction"]["state"] == "needs_review"
    assert any(d["code"] == "multiple_bibliographies" for d in report["extraction"]["diagnostics"])


def test_failed_pdf_extraction_makes_no_source_calls_and_preserves_existing_workspace(tmp_path):
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.5\ntruncated")
    root = tmp_path / "audit"
    root.mkdir()
    prior = (
        b'{"schema_version":3,"items":[],"verification_scope":{"mode":"all","eligible_keys":[]}}'
    )
    (root / "report.json").write_bytes(prior)

    def forbidden(*_):
        pytest.fail("Failed PDF extraction reached a source provider")

    with pytest.raises(ValueError):
        run_audit(
            source, output=root, client=FakeClient(), methods=fixture_registry({"test": forbidden})
        )
    assert (root / "report.json").read_bytes() == prior
    assert source.read_bytes() == b"%PDF-1.5\ntruncated"
    assert not (root / "report.tmp.json").exists()


def test_zero_reference_heading_is_not_a_successful_empty_audit(tmp_path):
    source = tmp_path / "emptyrefs.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    output.setFont("Times-Bold", 12)
    output.drawString(50, 700, "References")
    output.save()
    with pytest.raises(PDFExtractionError, match="reference occurrences"):
        extract_pdf(source)
    assert not source.with_name("emptyrefs.bib-lint").exists()


def test_scanned_reference_page_with_readable_heading_still_reports_ocr(tmp_path):
    source = tmp_path / "heading-and-scan.pdf"
    output = canvas.Canvas(str(source), invariant=1)
    output.setFont("Times-Bold", 12)
    output.drawString(50, 740, "References")
    _scan(output)
    output.save()
    with pytest.raises(PDFExtractionError) as failure:
        extract_pdf(source)
    assert any(
        d["code"] == "unreadable_reference_page" and d.get("page") == 1
        for d in failure.value.diagnostics
    )
