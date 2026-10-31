import copy
import hashlib
import json

import pytest
from defusedxml.common import EntitiesForbidden

from bib_lint.viewer.data import comparison_rows, pretty_xml, read_response, suggestions, table_rows


def fixture_report():
    entry = {
        "key": "sample",
        "type": "article",
        "fields": {"title": "Example", "year": "2024"},
        "persons": {},
    }
    method = {
        "name": "crossref",
        "status": "found",
        "authority": True,
        "agrees_with_consensus": True,
        "found_ref": {
            "url": "https://doi.org/10.1234/example",
            "identifiers": {"doi": "10.1234/example"},
        },
        "comparisons": [{"field": "year", "input": "2024", "found": 2025, "result": "mismatch"}],
        "differences": [{"field": "year", "input": "2024", "found": 2025, "result": "mismatch"}],
    }
    result = {"is_correct": False, "complete": True, "reason": "Year differs", "methods": [method]}
    item = {"entry": entry, "validations": {"is_used": True, "correctness": result}}
    unused = {"entry": {**entry, "key": "unused"}, "validations": {"is_used": False}}
    return {"schema_version": 2, "items": [item, unused]}


def test_all_rows_counts_and_status():
    rows = table_rows(fixture_report())
    assert len(rows) == 2
    assert list(rows[0]) == [
        "Citation key",
        "Used in paper",
        "Status",
        "Found",
        "Consensus",
        "Note",
    ]
    assert rows[0]["Found"] == rows[0]["Consensus"] == "1/1"
    assert rows[1]["Used in paper"] == "No"
    assert rows[1]["Status"] == "Skipped"


def test_comparisons_and_evidence_based_proposals():
    item = fixture_report()["items"][0]
    row = comparison_rows(item)[0]
    assert list(row) == ["Source", "URL", "Field", "Status", "Your value", "Source's value"]
    assert row["Source's value"] == "2025"
    assert suggestions(item)[0]["Suggested"] == "2025"
    uncertain = copy.deepcopy(item)
    uncertain["validations"]["correctness"]["is_correct"] = None
    assert suggestions(uncertain) == []


def test_comparisons_and_corrections_link_directly_to_their_source():
    item = fixture_report()["items"][0]
    assert comparison_rows(item)[0]["URL"] == "https://doi.org/10.1234/example"
    assert suggestions(item)[0]["URL"] == "https://doi.org/10.1234/example"


def test_cache_read_checks_integrity_without_modifying_files(tmp_path):
    raw = b"<html>Original\ncontent</html>"
    path = tmp_path / "sample" / "publisher_1.html"
    path.parent.mkdir()
    path.write_bytes(raw)
    entry = {"path": "sample/publisher_1.html", "sha256": hashlib.sha256(raw).hexdigest()}
    assert read_response(tmp_path, entry)[0] == raw
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Checksum"):
        read_response(tmp_path, entry)
    assert path.read_bytes() == b"changed"
    with pytest.raises(ValueError, match="Invalid cache path"):
        read_response(tmp_path, {**entry, "path": "../outside"})


def test_xml_pretty_print_disallows_entities():
    assert "\n  <title>" in pretty_xml("<feed><title>Example</title></feed>")
    with pytest.raises(EntitiesForbidden):
        pretty_xml('<!DOCTYPE x [<!ENTITY s "secret">]><x>&s;</x>')


def test_browser_summary_and_reference_detail(tmp_path):
    from bib_lint.viewer.app import ViewerSession
    from bib_lint.viewer.jobs import Registry

    path = tmp_path / "report.json"
    path.write_text(json.dumps(fixture_report()))
    session = ViewerSession(Registry(), path)
    state = session.state()
    assert state["summary"]["total"] == 2
    assert state["summary"]["completed"] == state["summary"]["eligible"] == 1
    assert state["summary"]["used"] == 1
    assert state["summary"]["statuses"] == {"Invalid": 1}
    assert state["summary"]["attention"] == 1
    detail = session.detail("sample")
    assert detail["entry"]["key"] == "sample"
    assert detail["suggestions"][0]["Suggested"] == "2025"
    assert detail["comparisons"][0]["Status"] == "Mismatch"
    assert detail["sources"][0]["Source"] == "crossref"
    with pytest.raises(ValueError, match="key not found"):
        session.detail("missing")
    assert session.state()["rows"] == state["rows"]


def test_attention_includes_ambiguous_and_partial_results():
    from bib_lint.viewer.presentation import reference_rows

    report = fixture_report()
    item = report["items"][0]
    item["validations"]["correctness"]["is_correct"] = None
    assert reference_rows(report)[0]["needs_attention"] is True
    assert reference_rows(report)[1]["needs_attention"] is False


def test_locator_diagnostics_keep_the_original_field_and_value_visible():
    item = fixture_report()["items"][0]
    item["validations"]["correctness"]["input_findings"] = [
        {
            "field": "arxiv",
            "result": "unknown",
            "message": "Conflicting locators",
            "input": [
                {"field": "url", "value": "https://arxiv.org/abs/2401.12345"},
                {"field": "eprint", "value": "2402.54321"},
            ],
        }
    ]
    value = comparison_rows(item)[0]["Your value"]
    assert "https://arxiv.org/abs/2401.12345" in value
    assert "eprint" in value and "2402.54321" in value


def test_source_counts_exclude_resolvers_and_do_not_claim_unqueried_providers():
    from bib_lint.viewer.presentation import reference_detail, reference_rows

    report = fixture_report()
    result = report["items"][0]["validations"]["correctness"]
    result["retrieval"] = {"next": 2, "resolved": True}
    result["methods"].append(
        {
            "name": "doi",
            "status": "not_applicable",
            "evidence_category": "resolver",
            "redirect_url": "https://proceedings.mlr.press/v235/example.html",
            "lookup_history": [{"strategy": "resolve"}],
        }
    )
    row = reference_rows(report)[0]
    assert row["records_found"] == row["sources_checked"] == 1
    detail = reference_detail(report["items"][0])
    assert "supplied link or identifier" in detail["lookup_summary"]
    resolver = detail["sources"][1]
    assert resolver["Status"] == ["Resolved"]
    assert resolver["URL"] == result["methods"][1]["redirect_url"]
    assert resolver["Lookup"] == "DOI resolution"


def test_pdf_diagnostic_is_not_repeated_in_the_reference_finding():
    from bib_lint.viewer.presentation import reference_rows

    report = fixture_report()
    message = "No reliable printed authors could be recovered"
    item = report["items"][0]
    item["validations"]["correctness"].update(reason=message, methods=[])
    item["validations"]["extraction"] = {
        "state": "needs_review",
        "diagnostics": [{"message": message}],
    }
    assert reference_rows(report)[0]["Note"].count(message) == 1


def test_legacy_unknown_scope_preserves_known_findings_in_summary():
    from bib_lint.viewer.presentation import reference_rows, summary

    report = fixture_report()
    report["items"][0]["validations"]["is_used"] = None
    result = summary(report, reference_rows(report))
    assert result["scope"] == "unknown" and result["used"] is None
    assert result["completed"] == result["attention"] == 1
    assert result["statuses"] == {"Invalid": 1}


def test_a_source_requiring_context_is_not_presented_as_a_query():
    from bib_lint.viewer.data import source_rows

    method = {
        "name": "pmlr",
        "status": "error",
        "requests": [],
        "lookup_history": [{"strategy": "search"}],
        "error": {"code": "incomplete_search", "message": "Missing volume context"},
    }
    row = source_rows([method])[0]
    assert row["Lookup"] == "Not queried"
    assert "Missing volume context" in row["Error"]


def test_a_report_file_is_never_used_as_the_output_directory(tmp_path):
    from bib_lint.viewer.presentation import metadata

    report = fixture_report()
    standalone = tmp_path / "saved-audit.json"
    standalone.write_text(json.dumps(report))
    assert metadata(report, standalone)["output_directory"] == ""
    workspace = tmp_path / "audit"
    workspace.mkdir()
    (workspace / "report.json").write_text(json.dumps(report))
    assert metadata(report, workspace)["output_directory"] == str(workspace)
    assert metadata(report, workspace / "report.json")["output_directory"] == str(workspace)


def test_a_review_finding_names_the_unverified_fields():
    report = fixture_report()
    result = report["items"][0]["validations"]["correctness"]
    result.update(
        is_correct=None, reason="Record identified, but some citation fields remain unverified"
    )
    result["methods"][0].update(
        differences=[],
        comparisons=[
            {"field": "authors", "result": "unknown", "input": "J. Smith", "found": "Jane Smith"}
        ],
    )
    assert table_rows(report)[0]["Note"] == "Unverified: authors"


def test_findings_preserve_input_problems_alongside_source_mismatches():
    report = fixture_report()
    result = report["items"][0]["validations"]["correctness"]
    result["input_findings"] = [{"field": "doi", "message": "Conflicting supplied identifiers"}]
    note = table_rows(report)[0]["Note"]
    assert "year" in note and "Conflicting supplied identifiers" in note
