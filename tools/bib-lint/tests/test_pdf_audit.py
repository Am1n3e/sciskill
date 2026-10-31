"""PDF workspaces preserve source bytes and reuse only sealed matching extraction."""

import copy
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest
from pdf_support import pdf_report
from provider_support import fixture_registry
from support import FakeClient

from bib_lint.audit import prepare_input, run_audit
from bib_lint.cli import main
from bib_lint.pdf_evidence import seal_extraction
from bib_lint.verification.matching import select_result


@pytest.fixture
def pdf_input(tmp_path, monkeypatch):
    source = tmp_path / "research paper.PDF"
    source.write_bytes(b"%PDF-1.5\nsynthetic boundary test")
    calls = []
    settings = {"max_pages": 200}

    def identity(path):
        return {
            "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "extractor": {"id": "pdfplumber", "version": "0.11.9"},
            "parser": {"id": "bib-lint-local", "version": "1"},
            "settings": settings.copy(),
        }

    def extract(path):
        calls.append(path)
        report = pdf_report()
        report["source"]["sha256"] = identity(path)["document_sha256"]
        report["extraction"]["document"]["sha256"] = identity(path)["document_sha256"]
        report["extraction"]["settings"] = settings.copy()
        return seal_extraction(report)

    monkeypatch.setitem(
        sys.modules,
        "bib_lint.pdf_input",
        SimpleNamespace(extract_pdf=extract, extraction_identity=identity),
    )
    return source, calls, settings


def _found(record, client):
    return select_result("test", record, [copy.deepcopy(record)], authority=True)


def audit(source, **kwargs):
    return run_audit(
        source, client=FakeClient(), methods=fixture_registry({"test": _found}), **kwargs
    )


def test_pdf_preview_resume_and_refresh_reuse_extraction(pdf_input):
    source, calls, _ = pdf_input
    original = source.read_bytes()
    workspace, preview, _ = audit(source, preview=True)
    assert preview["schema_version"] == 4
    assert not workspace.cache.exists()
    assert len(calls) == 1
    _, verified, _ = audit(source)
    assert verified["verification_run"]["complete"]
    assert len(calls) == 1
    _, refreshed, _ = audit(source, refresh=True, citation_key="PDF-REF-0001")
    assert refreshed["verification_run"]["complete"]
    assert len(calls) == 1 and source.read_bytes() == original


@pytest.mark.parametrize("change", ["bytes", "settings"])
def test_changed_pdf_identity_does_not_replace_saved_work(pdf_input, change):
    source, calls, settings = pdf_input
    workspace, _, _ = audit(source, preview=True)
    before = workspace.checkpoint.read_bytes()
    if change == "bytes":
        source.write_bytes(source.read_bytes() + b"\n% new bytes identical citations")
    else:
        settings["max_pages"] = 201
    with pytest.raises(ValueError, match="different inputs|new output"):
        audit(source)
    assert workspace.checkpoint.read_bytes() == before
    assert len(calls) == 1


def test_inline_pdf_evidence_tampering_is_not_a_resumable_input(pdf_input):
    source, _, _ = pdf_input
    workspace, _, _ = audit(source, preview=True)
    report = json.loads(workspace.checkpoint.read_text())
    report["items"][0]["entry"]["fields"]["title"] = "tampered"
    workspace.checkpoint.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="evidence checksum"):
        audit(source)


@pytest.mark.parametrize(
    "options", [{"aux": "cites.aux"}, {"encoding": "utf-8"}, {"include_source": True}]
)
def test_pdf_rejects_bibtex_options_before_extraction(pdf_input, options):
    source, calls, _ = pdf_input
    with pytest.raises(ValueError, match="PDF"):
        prepare_input(source, **options)
    assert not calls


def test_pdf_final_json_separates_coverage_from_verification(pdf_input, monkeypatch, capsys):
    source, _, _ = pdf_input
    monkeypatch.setattr("bib_lint.cli.run_audit", audit)
    assert main(["verify", str(source), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["complete"]
    assert result["extraction"] == {
        "state": "complete",
        "occurrence_count": 1,
        "unresolved_fragments": 0,
        "reference_pages": [1],
        "diagnostics": [],
    }


def test_same_pdf_bytes_under_a_new_name_can_resume(pdf_input, tmp_path):
    source, calls, _ = pdf_input
    output = tmp_path / "audit"
    audit(source, output=output, preview=True)
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(source.read_bytes())
    _, report, _ = audit(renamed, output=output)
    assert report["verification_run"]["complete"] and len(calls) == 1
    assert report["audit_input"]["path"] == str(renamed)
    assert json.loads((output / "report.json").read_text())["audit_input"]["path"] == str(renamed)


def test_pdf_extraction_failure_is_structured_and_preserves_workspace(
    pdf_input, monkeypatch, capsys
):
    source, _, _ = pdf_input

    class ExtractionFailure(ValueError):
        diagnostics = [{"code": "unreadable_reference_page", "message": "OCR required", "page": 1}]

    def fail(_path):
        raise ExtractionFailure("PDF references require OCR")

    monkeypatch.setattr(sys.modules["bib_lint.pdf_input"], "extract_pdf", fail)
    assert main(["verify", str(source), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["extraction"]["state"] == "failed"
    assert result["error"]["diagnostics"][0]["code"] == "unreadable_reference_page"
    assert not source.with_name("research paper.bib-lint").exists()


def test_pdf_workflow_applies_uncertainty_before_saving_source_outcomes(pdf_input, monkeypatch):
    source, _, _ = pdf_input
    module = sys.modules["bib_lint.pdf_input"]
    original_extract = module.extract_pdf

    def uncertain(path):
        report = original_extract(path)
        diagnostics = [
            {
                "code": "uncertain_year",
                "message": "Year interpretation is uncertain",
                "fields": ["year"],
            }
        ]
        report["items"][0]["pdf"]["diagnostics"] = diagnostics
        report["items"][0]["validations"]["extraction"] = {
            "state": "needs_review",
            "diagnostics": diagnostics,
        }
        return seal_extraction(report)

    def wrong_year(record, client):
        canonical = copy.deepcopy(record)
        canonical["year"] = "2024"
        return select_result("test", record, [canonical], authority=True)

    monkeypatch.setattr(module, "extract_pdf", uncertain)
    workspace, report, _ = run_audit(
        source, client=FakeClient(), methods=fixture_registry({"test": wrong_year})
    )
    item = report["items"][0]
    assert report["verification_run"]["orchestration_version"] == 7
    assert item["validations"]["correctness"]["is_correct"] is None
    assert item["validations"]["correctness"]["input_findings"][0]["code"] == "uncertain_year"
    saved = json.loads(workspace.final.read_text())
    assert saved["items"][0]["validations"]["correctness"]["is_correct"] is None


def test_legacy_json_verify_api_checks_pdf_identity_before_using_checkpoint(tmp_path):
    from bib_lint.verification import verify_file

    source = tmp_path / "input.json"
    destination = tmp_path / "output.json"
    checkpoint = tmp_path / "output.tmp.json"
    original = seal_extraction(pdf_report())
    changed = copy.deepcopy(original)
    changed["extraction"]["document"]["sha256"] = "b" * 64
    seal_extraction(changed)
    source.write_text(json.dumps(original))
    checkpoint.write_text(json.dumps(changed))
    before = checkpoint.read_bytes()
    with pytest.raises(ValueError, match="different inputs"):
        verify_file(
            source,
            output=destination,
            client=FakeClient(),
            methods=fixture_registry({"test": _found}),
        )
    assert checkpoint.read_bytes() == before
