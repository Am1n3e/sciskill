"""Only proven line-end hyphens permit alternate PDF presentation comparisons."""

import copy

from pdf_support import pdf_report

from bib_lint.pdf_evidence import apply_extraction
from bib_lint.status import reference_status
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import input_record, select_result


def _title_item(parts):
    item = pdf_report()["items"][0]
    title = "".join(
        part if index == 0 or parts[index - 1].endswith("-") else " " + part
        for index, part in enumerate(parts)
    )
    item["entry"]["fields"]["title"] = title
    item["entry"]["fields"]["doi"] = "10.1234/example"
    item["pdf"]["fragments"] = [
        {"page": 1, "x0": 50, "top": 100 + i * 12, "x1": 500, "bottom": 111 + i * 12, "text": part}
        for i, part in enumerate(parts)
    ]
    item["pdf"]["field_evidence"]["title"] = [
        {"fragment": i, "start": 0, "end": len(part)} for i, part in enumerate(parts)
    ]
    return item


def _decision(item, **changes):
    original = input_record(item["entry"])
    canonical = {**copy.deepcopy(original), **changes}
    method = select_result("primary", original, [canonical], authority=True)
    assert method["status"] == "found", (original, canonical)
    result = build_consensus([method])
    result["complete"] = True
    return result


def test_real_and_optional_hyphens_can_be_mixed_without_rewriting_input():
    item = _title_item(["Study of tool-", "use in code-", "bases for agents"])
    before = copy.deepcopy(item)
    result = _decision(item, title="Study of tool-use in codebases for agents")
    assert result["is_correct"] is False
    result = apply_extraction(result, item)
    assert result["is_correct"] is True
    assert reference_status({**item["validations"], "correctness": result}) == "Correct"
    assert item == before
    assert result["methods"][0]["comparisons"][0]["input"] == before["entry"]["fields"]["title"]


def test_a_different_title_typo_is_not_erased_by_line_end_hyphen_variants():
    item = _title_item(["Study of tool-", "use in code-", "bases for agents"])
    result = _decision(item, title="Study of tool-use in codebases for agants")
    result = apply_extraction(result, item)
    assert result["is_correct"] is False
    assert any(c["field"] == "title" for c in result["methods"][0]["differences"])


def test_inline_hyphen_with_identical_spelling_is_not_authorized_by_another_line_break():
    item = _title_item(["Study of tool-", "use and tool-use in agents"])
    result = _decision(item, title="Study of tool-use and tooluse in agents")
    result = apply_extraction(result, item)
    assert result["is_correct"] is False


def test_fragment_break_without_field_evidence_does_not_authorize_a_title_change():
    item = _title_item(["Study of code-", "bases for agents"])
    item["pdf"]["field_evidence"]["title"][0]["end"] -= 1
    result = _decision(item, title="Study of codebases for agents")
    assert apply_extraction(result, item)["is_correct"] is False


def test_presentation_variants_are_bounded_and_keep_the_original():
    from bib_lint.pdf_presentation import text_variants

    parts = ["many-", "small-", "line-", "end-", "hyphens-", "in-", "one title"]
    item = _title_item(parts)
    variants = text_variants(item, "title", item["entry"]["fields"]["title"])
    assert variants[0] == item["entry"]["fields"]["title"]
    assert 1 < len(variants) <= 16


def _author_item():
    item = pdf_report()["items"][0]
    fragments = ["Jane Smith and Antonin Kan-", "ervisto. Example Paper. Journal, 2025."]
    item["pdf"]["fragments"] = [
        {"page": 1, "x0": 50, "top": 100 + i * 12, "x1": 500, "bottom": 111 + i * 12, "text": text}
        for i, text in enumerate(fragments)
    ]
    item["pdf"]["field_evidence"]["authors"] = [
        {"fragment": 0, "start": 0, "end": len(fragments[0])},
        {"fragment": 1, "start": 0, "end": 7},
    ]
    person = {
        "first": ["Antonin"],
        "middle": [],
        "prelast": [],
        "last": ["Kan-ervisto"],
        "lineage": [],
        "kind": "person",
        "bibtex": "Antonin Kan-ervisto",
    }
    item["entry"]["persons"]["author"][0]["bibtex"] = "Jane Smith"
    item["entry"]["persons"]["author"].append(person)
    return item


def test_wrapped_author_family_matches_without_combinatorial_author_list_variants():
    item = _author_item()
    original = input_record(item["entry"])
    canonical = copy.deepcopy(original["authors"])
    canonical[1]["family"] = "Kanervisto"
    result = _decision(item, authors=canonical)
    before = copy.deepcopy(item)
    result = apply_extraction(result, item)
    assert result["is_correct"] is True
    assert item == before


def test_wrapped_author_does_not_hide_a_different_given_name():
    item = _author_item()
    canonical = copy.deepcopy(input_record(item["entry"])["authors"])
    canonical[1].update(given="David", family="Kanervisto")
    result = apply_extraction(_decision(item, authors=canonical), item)
    assert result["is_correct"] is False


def test_name_word_boundaries_are_never_collapsed_without_a_line_end_hyphen():
    item = _author_item()
    item["entry"]["persons"]["author"][1].update(
        prelast=["Kan"], last=["Ervisto"], bibtex="Antonin Kan Ervisto"
    )
    canonical = copy.deepcopy(input_record(item["entry"])["authors"])
    canonical[1]["family"] = "KanErvisto"
    result = apply_extraction(_decision(item, authors=canonical), item)
    assert result["is_correct"] is False


def test_uncertainty_remains_visible_after_a_legitimate_presentation_match():
    item = _title_item(["Study of code-", "bases for agents"])
    diagnostic = {
        "code": "clipped_text",
        "message": "Title is visibly clipped",
        "fields": ["title"],
    }
    item["pdf"]["diagnostics"] = [diagnostic]
    item["validations"]["extraction"] = {"state": "needs_review", "diagnostics": [diagnostic]}
    result = apply_extraction(_decision(item, title="Study of codebases for agents"), item)
    assert result["is_correct"] is None
    assert result["input_findings"][0]["code"] == "clipped_text"
    assert reference_status({**item["validations"], "correctness": result}) == "Needs review"


def test_index_only_evidence_does_not_gain_authoritative_presentation_matches():
    item = _title_item(["Study of code-", "bases for agents"])
    result = _decision(item, title="Study of codebases for agents")
    result["methods"][0]["authority"] = False
    original = copy.deepcopy(result)
    assert apply_extraction(result, item) == original


def test_normalized_accents_do_not_lose_the_proved_hyphen_position():
    item = _title_item(["E\u0301tude of code-", "bases for agents"])
    item["entry"]["fields"]["title"] = "Étude of code-bases for agents"
    result = apply_extraction(_decision(item, title="Étude of codebases for agents"), item)
    assert result["is_correct"] is True


def test_non_pdf_bibtex_hyphens_are_never_reinterpreted():
    item = _title_item(["Study of code-", "bases for agents"])
    item.pop("pdf")
    item["validations"].pop("extraction")
    result = _decision(item, title="Study of codebases for agents")
    assert apply_extraction(result, item)["is_correct"] is False


def test_many_proved_breaks_match_without_enumerating_exponential_variants():
    item = _title_item(
        [
            "A tool-",
            "use study of code-",
            "bases and reinforce-",
            "ment with multi-",
            "step memory and bench-",
            "marks for agents",
        ]
    )
    title = (
        "A tool-use study of codebases and reinforcement with multi-step memory "
        "and benchmarks for agents"
    )
    result = apply_extraction(_decision(item, title=title), item)
    assert result["is_correct"] is True


def test_many_proved_breaks_do_not_erase_an_unrelated_typo():
    item = _title_item(
        [
            "A tool-",
            "use study of code-",
            "bases and reinforce-",
            "ment with multi-",
            "step memory and bench-",
            "marks for agents",
        ]
    )
    title = (
        "A tool-use study of codebases and reinforcement with multi-step memory "
        "and benchmarks for agants"
    )
    result = apply_extraction(_decision(item, title=title), item)
    assert result["is_correct"] is False
