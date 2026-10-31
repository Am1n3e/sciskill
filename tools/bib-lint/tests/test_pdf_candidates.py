"""Nearby rejected PDF candidates can expose a discrepancy without proving identity."""

import copy

import pytest
from pdf_support import pdf_report

from bib_lint.pdf_evidence import apply_extraction
from bib_lint.status import reference_status
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import input_record, select_result

INPUT_TITLE = "CodeNav: Beyond tool-use to using real-world codebases with LLM agents Revisited"
FOUND_TITLE = "CodeNav: Beyond tool-use to using real-world codebases with LLM agents"


def _case():
    item = pdf_report()["items"][0]
    item["entry"]["fields"]["title"] = INPUT_TITLE
    original = input_record(item["entry"])
    found = {**copy.deepcopy(original), "title": FOUND_TITLE}
    method = select_result("arxiv", original, [found], authority=True)
    assert method["status"] == "not_found" and method["rejected_candidates"] == [found]
    result = build_consensus([method])
    result["complete"] = True
    return item, result, found


def _status(item, result):
    item["validations"]["correctness"] = result
    return reference_status(item["validations"])


def test_retrieved_near_title_with_same_complete_names_and_year_is_review_only():
    item, result, _ = _case()
    before = copy.deepcopy((item, result))
    updated = apply_extraction(result, item)
    assert _status(item, updated) == "Needs review" and updated["is_correct"] is None
    finding = updated["input_findings"][0]
    assert (
        finding.items()
        >= {
            "field": "title",
            "code": "candidate_title_discrepancy",
            "result": "unknown",
            "input": INPUT_TITLE,
            "found": FOUND_TITLE,
        }.items()
    )
    assert "identity unconfirmed" in finding["message"]
    assert updated["canonical_ref"] is None
    assert updated["methods"] == before[1]["methods"]
    assert item["entry"] == before[0]["entry"]
    assert result == before[1]


def test_compatible_initials_are_review_evidence_without_claiming_exact_names():
    item, result, found = _case()
    item["entry"]["persons"]["author"][0]["first"] = ["J."]
    updated = apply_extraction(result, item)
    assert updated["input_findings"][0]["found"] == found["title"]
    assert updated["is_correct"] is None


@pytest.mark.parametrize(
    "changed",
    [
        {"authors": [{"given": "Jane", "family": "Other"}]},
        {"authors": [{"given": "David", "family": "Smith"}]},
        {"authors": [{"given": "Jane", "family": "Smith"}, {"given": "Other", "family": "Person"}]},
        {"year": "2024"},
        {"title": "Completely unrelated research on another topic"},
        {"title": INPUT_TITLE},
    ],
)
def test_different_identity_or_unrelated_title_does_not_manufacture_review(changed):
    item, result, found = _case()
    found.update(changed)
    assert not apply_extraction(result, item)["input_findings"]


@pytest.mark.parametrize(
    "people",
    [
        [],
        [
            {
                "first": [],
                "middle": [],
                "prelast": [],
                "last": ["others"],
                "lineage": [],
                "kind": "others",
            }
        ],
    ],
)
def test_no_named_authors_or_only_others_cannot_support_candidate_review(people):
    item, result, _ = _case()
    item["entry"]["persons"]["author"] = people
    assert not apply_extraction(result, item)["input_findings"]


def test_truncated_author_prefix_cannot_prove_a_complete_compatible_list():
    item, result, _ = _case()
    item["entry"]["persons"]["author"].append(
        {
            "first": [],
            "middle": [],
            "prelast": [],
            "last": ["others"],
            "lineage": [],
            "kind": "others",
        }
    )
    assert not apply_extraction(result, item)["input_findings"]


def test_existing_direct_bibtex_decisions_are_unchanged():
    item, result, _ = _case()
    item["validations"].pop("extraction")
    item.pop("pdf")
    assert apply_extraction(result, item) == result
    assert _status(item, result) == "Unresolved"


def test_independent_reliable_source_mismatch_remains_invalid():
    item, result, _ = _case()
    authoritative = input_record(item["entry"])
    authoritative["year"] = "2024"
    method = select_result("primary", input_record(item["entry"]), [authoritative], authority=True)
    assert method["status"] == "found"
    result = build_consensus([*result["methods"], method])
    result["complete"] = True
    updated = apply_extraction(result, item)
    assert updated["is_correct"] is False and _status(item, updated) == "Invalid"
    assert updated["input_findings"][0]["code"] == "candidate_title_discrepancy"


def test_failed_methods_do_not_emit_rejected_candidate_review():
    item, result, _ = _case()
    result["methods"][0]["status"] = "error"
    assert not apply_extraction(result, item)["input_findings"]


def test_original_fragment_proven_author_hyphen_can_support_review():
    item, result, _ = _case()
    person = item["entry"]["persons"]["author"][0]
    person.update(last=["Sm-ith"], bibtex="Jane Sm-ith")
    item["pdf"]["fragments"] = [{"text": "Jane Sm-"}, {"text": "ith. " + INPUT_TITLE}]
    item["pdf"]["field_evidence"]["authors"] = [
        {"fragment": 0, "start": 0, "end": 8},
        {"fragment": 1, "start": 0, "end": 3},
    ]
    updated = apply_extraction(result, item)
    assert updated["input_findings"][0]["code"] == "candidate_title_discrepancy"
    # Inline hyphens lack the physical wrap proof and cannot be silently removed.
    item["pdf"]["field_evidence"]["authors"] = []
    assert not apply_extraction(result, item)["input_findings"]


def test_reversed_complete_author_list_does_not_support_candidate_review():
    item, result, found = _case()
    item["entry"]["persons"]["author"].append(
        {"first": ["Ada"], "middle": [], "prelast": [], "last": ["Example"], "lineage": []}
    )
    found["authors"] = [{"given": "Ada", "family": "Example"}, {"given": "Jane", "family": "Smith"}]
    assert not apply_extraction(result, item)["input_findings"]


def test_reapplying_extraction_does_not_duplicate_existing_candidate_findings():
    item, result, _ = _case()
    updated = apply_extraction(result, item)
    assert len(updated["input_findings"]) == 1
    assert apply_extraction(updated, item) == updated
