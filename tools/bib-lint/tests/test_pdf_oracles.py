"""The independent oracle keeps annotation targets distinct from printed content."""

from pdf_e2e.oracles import bibliography_bodies, rendered_text


def test_href_target_is_not_printed_metadata():
    text, targets = rendered_text(r"\href{https://arxiv.org/abs/9999.99999v9}{Visible title}.")
    assert text == "Visible title."
    assert targets == ["https://arxiv.org/abs/9999.99999v9"]
    assert "9999" not in text


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
