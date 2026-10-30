"""Independent metadata expectations for adversarial representation/identity traps."""

import copy
from dataclasses import asdict

import pytest
from metadata_support import RECORDS, entry

from bib_lint.parser import parse_string
from bib_lint.status import reference_status
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import (
    compare_fields,
    doi,
    input_record,
    normalize,
    same_record,
    select_result,
)


def author_result(left, right):
    return compare_fields({"authors": left}, {"authors": right})[1]["result"]


@pytest.mark.parametrize(
    "key,base,field,accepted,statuses",
    [
        (
            "adv_match_family_boundary_collision",
            "codenav",
            "authors",
            {"mismatch", "unknown"},
            {"Invalid", "Needs review"},
        ),
        (
            "adv_match_literal_prefix_collision",
            "codenav",
            "authors",
            {"mismatch", "unknown"},
            {"Invalid", "Needs review"},
        ),
        ("adv_match_doi_tex_escaped_percent", "datawise", "doi", {"match"}, {"Correct"}),
        ("adv_match_title_tex_emphasis", "codenav", "title", {"match"}, {"Correct"}),
        (
            "adv_consensus_arxiv_impostor_venue",
            "codenav",
            "venue",
            {"unknown", "mismatch"},
            {"Invalid", "Needs review"},
        ),
    ],
)
def test_source_linked_challenge_expectations(key, base, field, accepted, statuses):
    original = input_record(entry(key))
    source = select_result("primary", original, [RECORDS[base]["record"]], authority=True)
    assert source["status"] == "found"
    result = build_consensus([source])
    assert {c["field"]: c["result"] for c in source["comparisons"]}[field] in accepted
    assert reference_status({"correctness": result}) in statuses


@pytest.mark.parametrize(
    "value",
    [
        r"\emph{CodeNav}: Beyond tool-use",
        r"\textbf{\emph{CodeNav}}: Beyond tool-use",
        r"{\itshape CodeNav}: Beyond tool-use",
    ],
)
def test_standard_tex_fonts_preserve_displayed_title(value):
    assert normalize(value) == normalize("CodeNav: Beyond tool-use")


@pytest.mark.parametrize("command", ["phantom", "newcommand", "href", "write", "input"])
def test_unknown_or_nonpresentation_tex_commands_are_not_erased(command):
    assert normalize("\\" + command + "{CodeNav}") != normalize("CodeNav")


@pytest.mark.parametrize("value", [r"\\emph{CodeNav}", r"\bfseriesOther{CodeNav}"])
def test_escaped_commands_and_command_name_prefixes_are_not_presentation_markup(value):
    assert normalize(value) != normalize("CodeNav")


@pytest.mark.parametrize(
    "value",
    [
        "  HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58  ",
        r"HTTPS://doi.org/10.18653\%2Fv1\%2F2025.EMNLP-MAIN.58",
        "doi:10.18653/v1/2025.emnlp-main.58",
    ],
)
def test_equivalent_doi_representations_decode_without_tex_comment_loss(value):
    assert doi(value) == "10.18653/v1/2025.emnlp-main.58"


def test_doi_url_input_recognizes_wrapper_case_and_outer_whitespace():
    original = input_record(
        {"fields": {"url": "  HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58  "}}
    )
    assert original["identifiers"]["doi"] == "10.18653/v1/2025.emnlp-main.58"


@pytest.mark.parametrize(
    "venue",
    [
        "arXiv",
        "arXiv preprint",
        "arXiv e-prints",
        "arXiv:2406.12276v1",
        "arXiv preprint arXiv:2406.12276v1",
        "arXiv preprint arXiv:cs/9901001",
    ],
)
def test_real_arxiv_aliases_remain_equivalent(venue):
    record = input_record({"fields": {"journal": venue}})
    assert record["record_type"] == "preprint"
    assert compare_fields({"venue": venue}, {"venue": "arXiv"})[3]["result"] == "match"


@pytest.mark.parametrize(
    "venue", ["arXiv Research Society Proceedings", "Journal of nonarXiv Studies"]
)
def test_arxiv_word_inside_a_different_venue_is_not_an_archive_alias(venue):
    record = input_record({"fields": {"journal": venue, "eprint": "2406.12276v1"}})
    assert record["record_type"] == "publication"
    assert compare_fields({"venue": venue}, {"venue": "arXiv"})[3]["result"] == "unknown"


def test_given_and_family_boundaries_are_not_lost_when_clustering_sources():
    source = copy.deepcopy(RECORDS["codenav"]["record"])
    source["identifiers"] = {}
    source["venue"] = "Example venue"
    changed = copy.deepcopy(source)
    changed["authors"][0] = {"given": "", "family": "Tanmay Gupta", "suffix": ""}
    assert not same_record(source, changed)


def test_name_kind_survives_input_conversion_and_is_not_a_personal_author_prefix():
    entry = asdict(
        parse_string("@article{x,author={{Tanmay Gupta} and others},title={CodeNav}}").entries["x"]
    )
    authors = input_record(entry)["authors"]
    assert [a["kind"] for a in authors] == ["literal", "others"]
    assert author_result(authors, RECORDS["codenav"]["record"]["authors"]) in {
        "mismatch",
        "unknown",
    }


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (
            [{"given": "Juan Carlos", "family": "de la Cruz", "suffix": "Jr."}],
            [{"given": "Juan Carlos", "family": "de la Cruz", "suffix": "Jr."}],
            "match",
        ),
        (
            [{"given": "Jos\u00e9", "family": "Garc\u00eda"}],
            [{"given": r"Jos{\'e}", "family": r"Garc{\'i}a"}],
            "match",
        ),
        ([{"given": "T.", "family": "Gupta"}], [{"given": "Tanmay", "family": "Gupta"}], "unknown"),
        (
            [{"given": "", "family": "World Health Organization", "kind": "literal"}],
            [{"given": "", "family": "World Health Organization"}],
            "match",
        ),
        (
            [{"given": "", "family": "World Health Organization", "kind": "literal"}],
            [{"given": "", "family": "World Health Organization", "kind": "person"}],
            "unknown",
        ),
    ],
)
def test_structured_names_keep_legitimate_particles_suffixes_accents_and_initials(
    left, right, expected
):
    assert author_result(left, right) == expected


def test_legitimate_others_prefix_still_requires_matching_structured_authors():
    full = RECORDS["codenav"]["record"]["authors"]
    prefix = [full[0], {"given": "", "family": "others", "kind": "others"}]
    assert author_result(prefix, full) == "partial_match"
    prefix[0] = {"given": "", "family": "Tanmay Gupta", "kind": "literal"}
    assert author_result(prefix, full) in {"mismatch", "unknown"}
