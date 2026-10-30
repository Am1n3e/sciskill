"""Reject every incompatible JSON value type before using saved diagnostics."""

import json
from copy import deepcopy

import pytest
from support import ENTRY, FakeClient

from bib_lint.scope import validate_report
from bib_lint.verification import verify_file
from bib_lint.viewer.data import load_report

JSON_VALUES = [None, False, True, 0, 1.5, "text", [], {}]
FINDING = {"field": "url", "result": "unknown", "code": "invalid_url", "message": "Review URL"}


def report_with(findings):
    return {
        "schema_version": 3,
        "verification_scope": {"mode": "all", "eligible_keys": [ENTRY["key"]]},
        "items": [
            {
                "entry": deepcopy(ENTRY),
                "validations": {"correctness": {"methods": [], "input_findings": findings}},
            }
        ],
    }


def assert_rejected_without_mutation(tmp_path, report):
    # Exercise the public validation, viewer, and verification entry points.
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Input findings"):
        validate_report(report)
    with pytest.raises(ValueError, match="Input findings"):
        load_report(path)
    with pytest.raises(ValueError, match="Input findings"):
        verify_file(path, client=FakeClient())
    assert path.read_bytes() == before
    assert not path.with_name("report.tmp.json").exists()


@pytest.mark.parametrize("value", [v for v in JSON_VALUES if not isinstance(v, list)])
def test_findings_container_requires_list(tmp_path, value):
    assert_rejected_without_mutation(tmp_path, report_with(value))


@pytest.mark.parametrize("value", [v for v in JSON_VALUES if not isinstance(v, dict)])
def test_finding_requires_object(tmp_path, value):
    assert_rejected_without_mutation(tmp_path, report_with([value]))


@pytest.mark.parametrize("field", ["field", "code", "message", "result"])
@pytest.mark.parametrize("value", [v for v in JSON_VALUES if not isinstance(v, str)])
def test_diagnostic_members_require_text(tmp_path, field, value):
    finding = {**FINDING, field: value}
    assert_rejected_without_mutation(tmp_path, report_with([finding]))


@pytest.mark.parametrize("result", ["text", "match", "partial_match", "not_checked", ""])
def test_diagnostic_result_requires_supported_token(tmp_path, result):
    assert_rejected_without_mutation(tmp_path, report_with([{**FINDING, "result": result}]))


@pytest.mark.parametrize("field", ["field", "code", "message", "result"])
def test_required_diagnostic_members_cannot_be_omitted(tmp_path, field):
    finding = {k: v for k, v in FINDING.items() if k != field}
    assert_rejected_without_mutation(tmp_path, report_with([finding]))


@pytest.mark.parametrize("result", ["unknown", "mismatch"])
def test_supported_diagnostics_round_trip(tmp_path, result):
    report = report_with([{**FINDING, "result": result}])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    validate_report(report)
    assert load_report(path) == report


def test_empty_and_historical_diagnostics_remain_valid():
    report = report_with([])
    validate_report(report)
    del report["items"][0]["validations"]["correctness"]["input_findings"]
    validate_report(report)
