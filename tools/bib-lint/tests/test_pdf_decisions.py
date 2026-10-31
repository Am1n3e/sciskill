"""Uncertain PDF interpretation cannot fabricate scholarly discrepancies."""

import copy

import pytest
from pdf_support import pdf_report

from bib_lint.status import reference_status
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import input_record, select_result


def _case(*, warning_fields=None, changed=None):
    item = pdf_report()["items"][0]
    item["entry"]["fields"]["doi"] = "10.1234/example"
    record = input_record(item["entry"])
    if changed:
        record.update(changed)
    method = select_result("test", input_record(item["entry"]), [record], authority=True)
    if warning_fields is not None:
        diagnostics = [
            {
                "code": "ambiguous_metadata",
                "message": "Original field boundary is uncertain",
                "fields": warning_fields,
            }
        ]
        item["pdf"]["diagnostics"] = diagnostics
        item["validations"]["extraction"] = {"state": "needs_review", "diagnostics": diagnostics}
    result = build_consensus([method])
    result["complete"] = True
    return item, result


def _apply(item, result):
    from bib_lint.pdf_evidence import apply_extraction

    result = apply_extraction(result, item)
    item["validations"]["correctness"] = result
    return result, reference_status(item["validations"])


def test_reliably_extracted_clean_citation_can_be_correct():
    item, result = _case()
    result, status = _apply(item, result)
    assert result["is_correct"] is True and status == "Correct"


def test_uncertain_field_blocks_correct_even_with_all_source_matches():
    item, result = _case(warning_fields=["title"])
    result, status = _apply(item, result)
    assert result["is_correct"] is None and status == "Needs review"
    assert any(f["code"] == "ambiguous_metadata" for f in result["input_findings"])


def test_uncertain_title_mismatch_is_not_evidence_the_printed_title_is_invalid():
    item, result = _case(warning_fields=["title"], changed={"title": "Example Papor"})
    assert result["is_correct"] is False
    result, status = _apply(item, result)
    assert result["is_correct"] is None and status == "Needs review"
    check = next(c for c in result["methods"][0]["comparisons"] if c["field"] == "title")
    assert check["result"] == "unknown"
    assert not any(c["field"] == "title" for c in result["methods"][0]["differences"])


def test_reliable_year_discrepancy_survives_unrelated_author_uncertainty():
    item, result = _case(warning_fields=["authors"], changed={"year": "2024"})
    result, status = _apply(item, result)
    assert result["is_correct"] is False and status == "Invalid"
    assert any(c["field"] == "year" for c in result["methods"][0]["differences"])


def test_uncertain_occurrence_identity_cannot_establish_a_mismatch():
    item, result = _case(warning_fields=[], changed={"year": "2024"})
    result, status = _apply(item, result)
    assert result["is_correct"] is None and status == "Needs review"


def test_unverified_pdf_extraction_still_needs_review_when_no_source_is_found():
    item, _ = _case(warning_fields=["title"])
    result = build_consensus(
        [
            {
                "name": "test",
                "status": "error",
                "found_ref": None,
                "differences": [],
                "comparisons": [],
            }
        ]
    )
    result["complete"] = True
    result, status = _apply(item, result)
    assert result["is_correct"] is None and status == "Needs review"


def test_pdf_pending_status_is_preserved_during_partial_verification():
    item, result = _case(warning_fields=["title"])
    result["complete"] = False
    result, status = _apply(item, result)
    assert status == "Pending"


def test_existing_bibtex_decisions_remain_unchanged():
    item, result = _case(changed={"year": "2024"})
    item.pop("pdf")
    item["validations"].pop("extraction")
    before = copy.deepcopy(result)
    result, status = _apply(item, result)
    assert result == before and status == "Invalid"


@pytest.mark.parametrize("verdict", [None, True])
def test_saved_pdf_diagnostics_are_visible_even_before_verifier_recomputes(verdict):
    validations = {
        "extraction": {"state": "needs_review", "diagnostics": []},
        "correctness": {"complete": True, "is_correct": verdict, "methods": []},
    }
    assert reference_status(validations) == "Needs review"
