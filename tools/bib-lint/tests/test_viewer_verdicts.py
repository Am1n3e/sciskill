"""Final reference decisions are distinct from verification progress."""

import copy

import pytest
from test_viewer import fixture_report

from bib_lint.viewer.presentation import reference_detail, reference_rows, summary


def example(kind):
    item = fixture_report()["items"][0]
    item["entry"]["key"] = kind
    result = item["validations"]["correctness"]
    method = result["methods"][0]
    if kind != "invalid":
        result["is_correct"] = None
        method["differences"] = []
    if kind == "valid":
        result["is_correct"] = True
        method["comparisons"][0]["result"] = "match"
    elif kind == "partial":
        method["comparisons"][0]["result"] = "partial_match"
        result["reason"] = "Listed authors match; remaining authors are omitted"
    elif kind == "uncertain":
        method["comparisons"][0]["result"] = "unknown"
    elif kind == "missing":
        result["methods"] = [{"name": "arxiv", "status": "not_found"}]
    elif kind == "pending":
        item["validations"].pop("correctness")
    elif kind == "running":
        result["complete"] = False
    elif kind == "skipped":
        item["validations"]["is_used"] = False
    return item


@pytest.mark.parametrize(
    "kind,verdict,progress",
    [
        ("valid", "Valid", "processed"),
        ("invalid", "Invalid", "processed"),
        ("partial", "Unresolved", "processed"),
        ("uncertain", "Unresolved", "processed"),
        ("missing", "Unresolved", "processed"),
        ("pending", None, "pending"),
        ("running", None, "pending"),
        ("skipped", None, "skipped"),
    ],
)
def test_rows_and_expanded_details_use_three_final_verdicts(kind, verdict, progress):
    item = example(kind)
    original = copy.deepcopy(item)
    row = reference_rows({"items": [item]})[0]
    assert row["Status"] == verdict
    assert row["progress"] == progress
    assert reference_detail(item)["row"]["Status"] == verdict
    assert row["needs_attention"] == (verdict in {"Invalid", "Unresolved"})
    assert item == original
    if kind == "pending":
        assert row["Note"] == "Not processed yet"


def test_summary_counts_only_processed_verdicts_and_preserves_uncertainty_reasons():
    report = {
        "items": [
            example(k)
            for k in ("valid", "invalid", "partial", "uncertain", "missing", "pending", "skipped")
        ]
    }
    rows = reference_rows(report)
    result = summary(report, rows)
    assert result["statuses"] == {"Valid": 1, "Invalid": 1, "Unresolved": 3}
    assert result["total"] == 7 and result["eligible"] == 6
    assert result["completed"] == 5 and result["skipped"] == 1
    assert result["attention"] == 4
    assert "remaining authors are omitted" in rows[2]["Note"]
    assert "Unverified: year" in rows[3]["Note"]


@pytest.mark.parametrize(
    "agent_status,verdict", [("Correct", "Valid"), ("Needs review", "Unresolved")]
)
def test_agent_verdicts_use_the_same_labels_without_changing_stored_evidence(agent_status, verdict):
    item = example("valid")
    item["agent_review"] = {"status": agent_status, "summary": "Review", "comparisons": []}
    original = copy.deepcopy(item)
    row = reference_rows({"items": [item]})[0]
    detail = reference_detail(item)
    assert row["Status"] == "Valid"
    assert row["Agent"] == detail["agent_review"]["status"] == verdict
    assert row["needs_attention"] == (verdict == "Unresolved")
    assert item == original
