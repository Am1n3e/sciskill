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
    assert list(row) == ["Source", "Field", "Status", "Your value", "Source's value"]
    assert row["Source's value"] == "2025"
    assert suggestions(item)[0]["Suggested"] == "2025"
    uncertain = copy.deepcopy(item)
    uncertain["validations"]["correctness"]["is_correct"] = None
    assert suggestions(uncertain) == []


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
