"""PDF extraction coverage and evidence remain distinct from source verification."""

import json

import pytest

from bib_lint.pdf_evidence import seal_extraction
from bib_lint.viewer.data import load_report
from bib_lint.viewer.presentation import reference_detail, reference_rows, summary


def pdf_report():
    diagnostic = {
        "code": "ambiguous_title",
        "message": "The title boundary needs review.",
        "fields": ["title"],
    }
    item = {
        "entry": {
            "key": "pdf-ref-0001",
            "type": "misc",
            "fields": {"title": "A printed title", "year": "2024"},
            "persons": {},
        },
        "validations": {
            "extraction": {"state": "needs_review", "diagnostics": [diagnostic]},
            "correctness": {"complete": True, "is_correct": None, "methods": []},
        },
        "pdf": {
            "label": "7",
            "text": "A printed title. 2024.",
            "fragments": [
                {
                    "page": 2,
                    "x0": 40,
                    "top": 80,
                    "x1": 220,
                    "bottom": 95,
                    "text": "A printed title. 2024.",
                }
            ],
            "field_evidence": {
                "title": [{"fragment": 0, "start": 0, "end": 15}],
                "year": [{"fragment": 0, "start": 17, "end": 21}],
            },
            "uris": [
                {
                    "uri": "javascript:alert('inert')",
                    "page": 2,
                    "x0": 40,
                    "top": 80,
                    "x1": 220,
                    "bottom": 95,
                }
            ],
            "diagnostics": [diagnostic],
        },
    }
    report = {
        "schema_version": 4,
        "source": {"name": "paper.PDF", "sha256": "a" * 64},
        "items": [item],
        "verification_scope": {"mode": "all", "eligible_keys": ["pdf-ref-0001"]},
        "extraction": {
            "schema_version": 1,
            "document": {
                "name": "paper.PDF",
                "sha256": "a" * 64,
                "pages": 3,
                "page_sizes": [{"width": 612, "height": 792}] * 3,
            },
            "extractor": {"id": "pdfplumber", "version": "test"},
            "parser": {"id": "bib-lint-local", "version": "1"},
            "settings": {},
            "state": "needs_review",
            "reference_pages": [2],
            "unresolved_fragments": 1,
            "diagnostics": [{"code": "boundary_uncertain", "message": "Review page 2.", "page": 2}],
        },
    }

    return seal_extraction(report)


def test_summary_keeps_extraction_coverage_separate_from_completed_verification():
    report = pdf_report()
    result = summary(report, reference_rows(report))
    assert result["completed"] == 1
    assert result["used"] is None
    assert result["extraction"] == {
        "state": "needs_review",
        "occurrence_count": 1,
        "unresolved_fragments": 1,
        "reference_pages": [2],
        "diagnostics": report["extraction"]["diagnostics"],
    }


def test_pending_extraction_warning_already_needs_attention():
    report = pdf_report()
    report["items"][0]["validations"].pop("correctness")
    row = reference_rows(report)[0]
    assert row["Status"] == "Pending"
    assert row["needs_attention"] is True
    assert "title boundary" in row["Note"]


def test_reference_evidence_retains_original_fragments_and_uri_targets():
    item = pdf_report()["items"][0]
    detail = reference_detail(item)
    assert detail["pdf"] == item["pdf"]
    assert detail["pdf"]["uris"][0]["uri"].startswith("javascript:")
    assert detail["extraction"] == item["validations"]["extraction"]


def test_schema_four_loader_rejects_missing_provenance(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"schema_version": 4, "items": []}))
    with pytest.raises(ValueError):
        load_report(path)


def test_pdf_report_reload_exposes_coverage_and_evidence_without_lookups(tmp_path):
    from bib_lint.viewer.app import ViewerSession
    from bib_lint.viewer.jobs import Registry

    path = tmp_path / "report.json"
    report = pdf_report()
    path.write_text(json.dumps(report))
    session = ViewerSession(Registry(), path)
    state = session.state()
    assert state["error"] is None
    assert state["extraction"] == report["extraction"]
    assert state["summary"]["completed"] == 1
    assert state["summary"]["extraction"]["state"] == "needs_review"
    assert state["metadata"]["input_kind"] == "pdf"
    detail = session.detail("pdf-ref-0001")
    assert detail["pdf"]["fragments"][0]["page"] == 2
    assert detail["pdf"]["uris"][0]["uri"].startswith("javascript:")
    assert not (tmp_path / "cache").exists()


def test_annotation_only_field_provenance_reloads_without_becoming_printed_text(tmp_path):
    from bib_lint.viewer.app import ViewerSession
    from bib_lint.viewer.jobs import Registry

    report = pdf_report()
    item = report["items"][0]
    item["entry"]["fields"]["doi"] = "10.1234/example"
    item["pdf"]["uris"][0]["uri"] = "https://doi.org/10.1234/example"
    item["pdf"]["field_evidence"]["doi"] = [{"uri": 0}]
    seal_extraction(report)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    detail = ViewerSession(Registry(), path).detail("pdf-ref-0001")
    assert detail["pdf"]["field_evidence"]["doi"] == [{"uri": 0}]
    assert "10.1234/example" not in detail["pdf"]["fragments"][0]["text"]
    assert detail["pdf"]["uris"][0]["uri"] == "https://doi.org/10.1234/example"
