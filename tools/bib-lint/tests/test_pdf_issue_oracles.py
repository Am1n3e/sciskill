"""Required locator defects need precise evidence, not an unrelated same-field warning."""

import pytest
from pdf_e2e.issues import assert_locator_issue


def _item(finding):
    return {"validations": {"correctness": {"input_findings": [finding], "methods": []}}}


def _case(key):
    return {"source_key": key, "case_id": "test/" + key}


def _finding(code, value, field="arxiv"):
    return {"field": field, "code": code, "result": "unknown", "input": value}


@pytest.mark.parametrize(
    "finding",
    [
        _finding("unverified_identifier", [{"identifier": "2406.12276v1"}]),
        _finding("identifier_mismatch", [{"identifier": "9999.99999v1"}]),
        _finding("missing_year", "2411.15124v5"),
        {"field": "arxiv", "result": "mismatch", "input": "2411.15124v5"},
    ],
)
def test_unrelated_same_field_issue_cannot_satisfy_specific_conflicting_locator(finding):
    with pytest.raises(AssertionError, match="precise locator"):
        assert_locator_issue(
            _item(finding), {"field": "arxiv"}, _case("adv_provider_split_arxiv_url")
        )


def test_exact_conflicting_locator_inside_nested_comparison_is_accepted():
    finding = _finding("identifier_mismatch", [{"identifier": "2411.15124v5"}])
    item = {
        "validations": {
            "correctness": {
                "methods": [{"comparisons": [{"field": "arxiv", "input_findings": [finding]}]}]
            }
        }
    }
    assert_locator_issue(item, {"field": "arxiv"}, _case("adv_provider_split_arxiv_url"))


@pytest.mark.parametrize("value", ["2406.12276v1", "2406.12276v1v", "2406.12276v1v50"])
def test_malformed_complete_identifier_cannot_be_replaced_with_a_valid_prefix(value):
    with pytest.raises(AssertionError, match="precise locator"):
        assert_locator_issue(
            _item(_finding("invalid_identifier", {"eprint": value})),
            {"field": "arxiv"},
            _case("adv_match_arxiv_double_version"),
        )


def test_complete_malformed_identifier_is_detected():
    assert_locator_issue(
        _item(_finding("invalid_identifier", {"eprint": "2406.12276v1v5"})),
        {"field": "arxiv"},
        _case("adv_match_arxiv_double_version"),
    )


def test_found_value_or_message_does_not_replace_missing_input_evidence():
    finding = _finding("identifier_mismatch", "2406.12276v1")
    finding.update(found="2406.12276v999", message="bad 2406.12276v999")
    with pytest.raises(AssertionError, match="precise locator"):
        assert_locator_issue(
            _item(finding), {"field": "arxiv"}, _case("adv_provider_shadowed_version_pin")
        )


def test_duplicate_forum_query_requires_both_supplied_ids():
    issue, case = {"field": "openreview"}, _case("adv_provider_duplicate_forum_id")
    finding = _finding("conflicting_identifiers", [{"identifier": "gy7fpSzJqz"}], "openreview")
    with pytest.raises(AssertionError, match="precise locator"):
        assert_locator_issue(_item(finding), issue, case)
    finding["input"].append({"identifier": "M1fd9Z00sj"})
    assert_locator_issue(_item(finding), issue, case)


@pytest.mark.parametrize(
    "value",
    ["10.18653/v1/2025.EMNLP-MAIN.58", "HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58"],
)
def test_nested_doi_issue_requires_the_complete_nested_wrapper(value):
    with pytest.raises(AssertionError, match="precise locator"):
        assert_locator_issue(
            _item(_finding("invalid_identifier", {"doi": value}, "doi")),
            {"field": "doi", "requirement": "typeset_nested_doi_url"},
            _case("adv_match_clean_doi_encoded"),
        )


def test_complete_nested_doi_wrapper_is_accepted():
    value = "https://doi.org/HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58"
    assert_locator_issue(
        _item(_finding("invalid_identifier", {"doi": value}, "doi")),
        {"field": "doi", "requirement": "typeset_nested_doi_url"},
        _case("adv_match_clean_doi_encoded"),
    )
