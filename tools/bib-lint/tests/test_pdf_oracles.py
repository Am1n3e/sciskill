"""The independent oracle keeps annotation targets distinct from printed content."""

from pdf_e2e.oracles import bibliography_bodies, rendered_text


def test_href_target_is_not_printed_metadata():
    text, targets = rendered_text(r"\href{https://arxiv.org/abs/9999.99999v9}{Visible title}.")
    assert text == "Visible title."
    assert targets == ["https://arxiv.org/abs/9999.99999v9"]
    assert "9999" not in text


def test_encoded_url_percent_is_literal_inside_native_url_macros():
    text, _ = rendered_text(r"\doi{HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58}")
    assert text == "doi: HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58"


def test_native_bibliography_order_includes_empty_occurrences():
    bodies = bibliography_bodies(
        r"\begin{thebibliography}{}\bibitem[ref()]{ref0002}"
        r"\bibitem[A(2024)]{ref0001}Author.\newblock Title.\end{thebibliography}"
    )
    assert [key for key, _ in bodies] == ["ref0002", "ref0001"]
    assert rendered_text(bodies[0][1])[0] == ""
    assert rendered_text(bodies[1][1])[0] == "Author. Title."


def test_rule_mutations_and_clean_controls_have_specific_verification_expectations():
    from pdf_e2e.build import FIXTURES, read_json
    from pdf_e2e.oracles import _required_checks, expected_statuses

    truth = read_json(FIXTURES / "truth.json")
    cases = {
        case["citation_key"]: case for case in truth["cases"] if case["corpus"] == "rule-variants"
    }
    clean = cases["case_clean"]
    year_wrong = cases["case_year_wrong"]
    assert {"field": "year", "results": ["mismatch"]} in _required_checks(year_wrong, "iclr")
    assert {"field": "title", "results": ["match"]} in _required_checks(clean, "iclr")
    assert expected_statuses(clean, "iclr", {"title": "text", "year": "text", "url": "text"}) == [
        "Correct"
    ]
    assert expected_statuses(clean, "icml", {"title": "text", "year": "text", "url": "text"}) == [
        "Needs review"
    ]


def test_initial_author_styles_keep_detectable_wrong_initials_and_mark_compatible_ones_unknown():
    from pdf_e2e.build import FIXTURES, read_json
    from pdf_e2e.oracles import _required_checks

    cases = {
        case["citation_key"]: case
        for case in read_json(FIXTURES / "truth.json")["cases"]
        if case["corpus"] == "rule-variants"
    }
    assert {"field": "authors", "results": ["mismatch"]} in _required_checks(
        cases["case_authors_wrong_given"], "icml"
    )
    assert {"field": "authors", "results": ["unknown"]} in _required_checks(
        cases["case_clean"], "icml"
    )


def test_literal_escaped_braces_are_presentation_not_tex_commands():
    text, _ = rendered_text(r"\{{S}\}ee\{{C}\}lick: \{{GUI}\}")
    assert text == "SeeClick: GUI"


def test_printed_unknown_markers_and_ijcai_labels_are_occurrences():
    from pdf_e2e.oracles import occurrence_classification

    assert occurrence_classification("????", "aaai") == "text"
    assert occurrence_classification("", "ijcai") == "text"
    assert occurrence_classification("", "iclr") == "omitted"


def test_field_equivalence_preserves_word_boundaries_and_only_relaxes_observed_wrap_hyphens():
    from pdf_e2e.oracles import equivalent_text

    fragments = [{"text": "Noah Dor-"}, {"text": "mann. Another title."}]
    assert equivalent_text("Dor-mann", "Dormann", fragments)
    assert not equivalent_text("Tool-use", "Tooluse", [])
    assert not equivalent_text("Tanmay Gupta", "TanmayGupta", [])
    assert equivalent_text("{S}ee{C}lick: {GUI}", "SeeClick: GUI", [])


def test_discretionary_hyphen_can_precede_uppercase_only_at_an_observed_break():
    from pdf_e2e.oracles import equivalent_text

    assert equivalent_text(
        "Code-Nav: Beyond", "CodeNav: Beyond", [{"text": "(2024). Code-"}, {"text": "Nav: Beyond"}]
    )
    assert not equivalent_text("Code-Nav: Beyond", "CodeNav: Beyond", [])


def test_native_author_truncation_is_derived_from_renderer_not_hidden_source_people():
    from pdf_e2e.oracles import printed_authors

    people = [
        {"given": str(i), "family": f"Family{i}", "suffix": "", "kind": "person"} for i in range(23)
    ]
    body = "First Family0, Second Family1, and 21 others. 2025. A title."
    assert printed_authors(people, body) == people[:2] + [
        {"given": "", "family": "others", "suffix": "", "kind": "others"}
    ]
    assert printed_authors(people[:2], "First Family0 and Second Family1. 2025.") == people[:2]


def test_protected_source_name_grouping_is_explicitly_unrecoverable_after_rendering():
    from pdf_e2e.oracles import author_structure_visible

    normal = {"given": "Ada", "family": "Example", "suffix": "Jr.", "kind": "person"}
    assert author_structure_visible([normal])
    assert not author_structure_visible([{**normal, "given": "Youngjune Gwon and Yeong-Dae"}])
    assert not author_structure_visible([{**normal, "suffix": "Zhiyong"}])


def test_literal_person_braces_are_erased_but_full_name_survives_initial_styles():
    from pdf_e2e.build import FIXTURES, read_json
    from pdf_e2e.oracles import expected_statuses

    case = next(
        case
        for case in read_json(FIXTURES / "truth.json")["cases"]
        if case["citation_key"] == "adv_match_literal_prefix_collision"
    )
    assert expected_statuses(case, "icml", {"title": "text", "year": "text"}) == ["Partial match"]


def test_locator_erasure_is_physical_and_changes_verdict_without_dropping_checks():
    from pdf_e2e.build import FIXTURES, read_json
    from pdf_e2e.oracles import _required_checks, arxiv_locator_visible, expected_statuses

    uri = "https://arxiv.org/abs/2406.12276v1"
    assert arxiv_locator_visible("arXiv:2406.12276v1", [], [])
    assert arxiv_locator_visible("arXiv:2406.12276", [], [])
    assert arxiv_locator_visible("Visible title", [uri], [uri])
    assert not arxiv_locator_visible("Visible title", [uri], [])
    case = next(
        c
        for c in read_json(FIXTURES / "truth.json")["cases"]
        if c["citation_key"] == "case_year_wrong"
    )
    assert expected_statuses(
        case, "ijcai", {"title": "text", "year": "text"}, arxiv_locator_erased=True
    ) == ["Needs review"]
    assert {"field": "year", "results": ["mismatch"]} in _required_checks(case, "ijcai")


def test_all_primary_field_assertion_does_not_accept_one_matching_source():
    import pytest
    from test_pdf_e2e import _assert_checks

    item = {
        "pdf": {"diagnostics": []},
        "validations": {
            "correctness": {
                "methods": [
                    {
                        "name": "arxiv",
                        "status": "found",
                        "authority": True,
                        "comparisons": [{"field": "year", "result": "mismatch"}],
                    },
                    {
                        "name": "openreview",
                        "status": "found",
                        "authority": True,
                        "comparisons": [{"field": "year", "result": "match"}],
                    },
                ]
            }
        },
    }
    expected = {
        "case_id": "controlled/year-error",
        "expected_fields": {"year": "2021"},
        "required_checks": [
            {"field": "year", "source": "all_authoritative_found", "results": ["mismatch"]}
        ],
        "required_issues": [],
        "expected_statuses": [],
    }
    with pytest.raises(AssertionError, match="all authoritative"):
        _assert_checks(item, expected)


def test_unprinted_contradictory_venue_does_not_become_a_pdf_error():
    from pdf_e2e.build import FIXTURES, read_json
    from pdf_e2e.oracles import expected_statuses, visible_checks

    case = next(
        case
        for case in read_json(FIXTURES / "truth.json")["cases"]
        if case["citation_key"] == "adv_consensus_shadowed_journal"
    )
    visibility = {"title": "text", "year": "text", "booktitle": "text", "journal": "omitted"}
    assert visible_checks(case, "iclr", visibility) == []
    assert expected_statuses(case, "iclr", visibility) == ["Correct"]
    visibility["journal"] = "text"
    assert visible_checks(case, "iclr", visibility) == [{"field": "venue", "results": ["unknown"]}]


def test_missing_printed_fields_cannot_be_filled_from_canonical_metadata():
    import pytest
    from test_pdf_e2e import _assert_fields

    item = {
        "entry": {"fields": {"year": "2024"}, "persons": {}},
        "pdf": {
            "text": "A title without a date.",
            "fragments": [{"page": 1, "text": "A title without a date."}],
        },
    }
    expected = {
        "case_id": "rule-variants/year_missing",
        "expected_fields": {},
        "expected_authors": [],
        "absent_fields": ["year"],
    }
    with pytest.raises(AssertionError, match="unprinted field"):
        _assert_fields(item, expected)


def test_native_double_doi_wrappers_are_recorded_from_actual_uri_evidence():
    from pdf_e2e.oracles import typeset_locator_issues

    target = "https://doi.org/HTTPS://doi.org/10.18653%2Fv1%2F2025.emnlp-main.58"
    assert typeset_locator_issues([target], [target]) == [
        {"field": "doi", "code": "typeset_nested_doi_url"}
    ]
    assert typeset_locator_issues([target], []) == []
    assert (
        typeset_locator_issues(["https://doi.org/10.18653/v1/2025.emnlp-main.58"], [target]) == []
    )


def test_gold_inventory_cannot_silently_drop_or_duplicate_compiled_projects():
    import pytest
    from pdf_e2e.oracles import validate_gold_inventory

    first = {"venue": "iclr", "corpus": "rules", "pdf_sha256": "aaa"}
    second = {"venue": "acl", "corpus": "rules", "pdf_sha256": "bbb"}
    ledger = {"complete": True, "renderable_builds": [first, second], "renderable_counterparts": []}
    validate_gold_inventory({"projects": [first, second]}, ledger)
    for rows in ([first], [first, first, second]):
        with pytest.raises(ValueError, match="inventory"):
            validate_gold_inventory({"projects": rows}, ledger)


def test_physical_reference_anchor_rejects_fake_page_or_whole_page_box():
    import pytest
    from test_pdf_e2e import _assert_anchor

    expected = {"case_id": "controlled/physical", "anchor": {"page": 2, "box": [60, 90, 300, 102]}}
    good = {"page": 2, "x0": 60, "top": 90, "x1": 300, "bottom": 102}
    _assert_anchor({"pdf": {"fragments": [good]}}, expected)
    for wrong in ({**good, "page": 1}, {**good, "x0": 0, "top": 0, "x1": 600, "bottom": 800}):
        with pytest.raises(AssertionError, match="physical"):
            _assert_anchor({"pdf": {"fragments": [wrong]}}, expected)


def test_representative_people_require_given_names_not_only_families():
    import pytest
    from test_pdf_e2e import _assert_fields

    expected = {
        "case_id": "representative-20/example",
        "expected_fields": {},
        "expected_authors": [{"given": "Ada", "family": "Example", "suffix": "", "kind": "person"}],
    }
    item = {
        "entry": {"fields": {}, "persons": {"author": [{"first": ["Wrong"], "last": ["Example"]}]}},
        "pdf": {
            "text": "Ada Example. Title.",
            "fragments": [{"page": 2, "text": "Ada Example. Title."}],
        },
    }
    with pytest.raises(AssertionError, match="given name"):
        _assert_fields(item, expected)


def test_printed_doi_must_survive_complete_not_just_prefix_or_annotation():
    import pytest
    from test_pdf_e2e import _assert_fields

    expected = {
        "case_id": "controlled/doi",
        "expected_fields": {"doi": "HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58"},
        "expected_authors": [],
    }
    item = {
        "entry": {"fields": {"doi": "10.18653/v1/2025.emnlp-main"}, "persons": {}},
        "pdf": {
            "text": "doi:10.18653/v1/2025.emnlp-main.58",
            "fragments": [{"page": 1, "text": "doi:10.18653/v1/2025.emnlp-main.58"}],
        },
    }
    with pytest.raises(AssertionError, match="doi"):
        _assert_fields(item, expected)
    item["entry"]["fields"]["doi"] += ".58"
    _assert_fields(item, expected)


def test_unlinked_title_candidate_requires_precise_review_and_stays_unselected():
    import copy

    import pytest
    from test_pdf_e2e import _assert_candidate_review

    expected = {
        "case_id": "controlled/title",
        "candidate_review": {"input": "CodeNav Revisited", "found": "CodeNav", "source": "arxiv"},
    }
    finding = {
        "field": "title",
        "code": "candidate_title_discrepancy",
        "input": "CodeNav Revisited",
        "found": "CodeNav",
        "result": "unknown",
    }
    item = {
        "pdf": {"fragments": []},
        "validations": {
            "correctness": {
                "input_findings": [finding],
                "canonical_ref": None,
                "methods": [
                    {
                        "name": "arxiv",
                        "status": "not_found",
                        "found_ref": None,
                        "rejected_candidates": [{"title": "CodeNav"}],
                    }
                ],
            }
        },
    }
    _assert_candidate_review(item, expected)
    for changed in ({"code": "unrelated"}, {"found": "Different"}, {"result": "mismatch"}):
        wrong = copy.deepcopy(item)
        wrong["validations"]["correctness"]["input_findings"][0].update(changed)
        with pytest.raises(AssertionError, match="candidate"):
            _assert_candidate_review(wrong, expected)
    wrong = copy.deepcopy(item)
    wrong["validations"]["correctness"]["canonical_ref"] = {"title": "CodeNav"}
    with pytest.raises(AssertionError, match="candidate"):
        _assert_candidate_review(wrong, expected)


def test_only_others_needs_an_explicit_missing_authors_diagnostic():
    import pytest
    from test_pdf_e2e import _assert_fields

    expected = {
        "case_id": "controlled/others",
        "expected_fields": {},
        "expected_authors": [{"given": "", "family": "others", "suffix": "", "kind": "others"}],
    }
    item = {
        "entry": {"fields": {}, "persons": {"author": [{"last": ["others"]}]}},
        "pdf": {
            "text": "others. A title.",
            "fragments": [{"page": 1, "text": "others. A title."}],
            "diagnostics": [{"code": "unrelated", "fields": ["authors"]}],
        },
    }
    with pytest.raises(AssertionError, match="missing_authors"):
        _assert_fields(item, expected)
    item["pdf"]["diagnostics"][0]["code"] = "missing_authors"
    _assert_fields(item, expected)
