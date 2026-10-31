"""Independent adversarial examples for local citation text and layout parsing."""

import pytest

from bib_lint.pdf_input.citations import parse_reference
from bib_lint.pdf_input.layout import bibliography_lines, occurrences


def line(text, *, page=1, x=50, top=100, font="Times-Roman", column=0):
    return {
        "text": text,
        "page": page,
        "x0": x,
        "x1": 550,
        "top": top,
        "bottom": top + 10,
        "_column": column,
        "_spans": [{"start": 0, "end": len(text), "font": font, "size": 10}],
    }


def citation(text, **kwargs):
    return parse_reference([line(text, **kwargs)], "pdf-ref-0001", [])


def test_eccv_colon_separates_inverted_authors_from_title():
    item = citation(
        "[1] Gupta, T., Weihs, L., Kembhavi, A.: CodeNav: Beyond tool-use to real codebases. "
        "In: International Conference on Learning Representations (2024)."
    )
    assert item["entry"]["fields"]["title"] == "CodeNav: Beyond tool-use to real codebases"
    assert [p["last"] for p in item["entry"]["persons"]["author"]] == [
        ["Gupta"],
        ["Weihs"],
        ["Kembhavi"],
    ]
    assert "CodeNav" not in item["entry"]["fields"].get("journal", "")


def test_doi_year_like_digits_do_not_replace_publication_year():
    item = citation("Jane Smith. Example Paper. Example Journal, 2025. doi:10.1234/2024.98765.")
    assert item["entry"]["fields"]["year"] == "2025"
    assert item["entry"]["fields"]["doi"] == "10.1234/2024.98765"


def test_access_date_does_not_replace_publication_year():
    item = citation("Jane Smith. Example Paper. Example Journal, 2024. Accessed January 2025.")
    assert item["entry"]["fields"]["year"] == "2024"


def test_year_at_end_of_actual_title_is_preserved():
    item = citation("Jane Smith. Benchmark 2024. Example Journal, 2025.")
    assert item["entry"]["fields"]["title"] == "Benchmark 2024"
    assert item["entry"]["fields"]["year"] == "2025"


def test_corporate_author_with_and_is_not_split_into_invented_people():
    item = citation(
        "The OpenAI Research and Development Group. Agent Evaluation. Example Journal, 2025."
    )
    people = item["entry"]["persons"].get("author", [])
    assert len(people) == 1
    assert people[0]["kind"] == "literal"
    assert people[0]["last"] == ["The OpenAI Research and Development Group"]
    assert item["entry"]["fields"]["title"] == "Agent Evaluation"


def test_printed_suffix_does_not_become_surname():
    item = citation("John Smith Jr. and Jane Doe. Example Paper. Example Journal, 2025.")
    first = item["entry"]["persons"]["author"][0]
    assert first["last"] == ["Smith"]
    assert first["lineage"] == ["Jr."]


def test_full_name_and_parenthetical_native_alias_keep_the_real_family():
    item = citation("Sujian Li (李素建) and Jane Doe. Example Paper. Example Journal, 2025.")
    first = item["entry"]["persons"]["author"][0]
    assert first["first"] == ["Sujian"]
    assert first["last"] == ["Li"]
    assert "李素建" in item["pdf"]["fragments"][0]["text"]


def test_quoted_title_can_contain_sentence_punctuation():
    item = citation('Jane Smith. "Why do agents fail? A study of memory." Example Journal, 2025.')
    assert item["entry"]["fields"]["title"] == "Why do agents fail? A study of memory"


def test_wrapped_url_does_not_swallow_the_next_sentence():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Example Journal, 2025."),
            line("https://example.org/paper.", x=65, top=113),
            line("Accessed January 2026.", x=65, top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["url"] == "https://example.org/paper"
    assert "paper. Accessed" in item["pdf"]["text"]


def test_doi_surrounding_parenthesis_is_not_part_of_identifier():
    item = citation("Jane Smith. Example Paper. Example Journal, 2025. (doi:10.1234/example).")
    assert item["entry"]["fields"]["doi"] == "10.1234/example"


def test_missing_authors_cannot_confidently_turn_title_into_a_person():
    item = citation("CodeNav: Beyond tool-use to real codebases. Example Journal, 2024.")
    assert item["validations"]["extraction"]["state"] == "needs_review"
    assert any("authors" in d["fields"] for d in item["pdf"]["diagnostics"])


def test_doi_at_start_of_continuation_line_is_not_a_numbered_reference():
    groups = occurrences(
        [
            line("[1] Jane Smith. Example Paper. Example Journal, 2025."),
            line("10.1234/example", x=65, top=113),
            line("[2] John Doe. Another Paper. Example Journal, 2024.", top=140),
        ]
    )
    assert len(groups) == 2
    assert [f["text"] for f in groups[0]][-1] == "10.1234/example"


def test_bold_initial_in_reference_is_not_an_appendix_heading():
    rows = [
        line("References", font="Times-Bold"),
        line("A. Smith. Example Paper. Example Journal, 2025.", font="Times-Bold", top=125),
        line("Jane Doe. Another Paper. Example Journal, 2024.", top=150),
    ]
    selected, _ = bibliography_lines([rows])
    assert [f["text"] for f in selected] == [rows[1]["text"], rows[2]["text"]]


def test_repeated_running_header_is_excluded_from_reference_fragments():
    header = "Manuscript under review"
    pages = [
        [
            line(header, top=50),
            line("References", top=100, font="Times-Bold"),
            line("Jane Smith. Example Paper. Example Journal, 2025.", top=125),
        ],
        [
            line(header, page=2, top=50),
            line("John Doe. Another Paper. Example Journal, 2024.", page=2, top=100),
        ],
    ]
    selected, _ = bibliography_lines(pages)
    assert all(f["text"] != header for f in selected)
    assert len(selected) == 2


@pytest.mark.parametrize("label", ["[1]", "1."])
def test_duplicate_printed_labels_remain_distinct_occurrences(label):
    groups = occurrences(
        [
            line(f"{label} Jane Smith. Example Paper. Example Journal, 2025."),
            line(f"{label} Jane Smith. Example Paper. Example Journal, 2025.", top=130),
        ]
    )
    assert len(groups) == 2


def test_field_provenance_selects_supporting_text_instead_of_the_entire_reference():
    item = parse_reference(
        [
            line("[1] Jane Smith and John Doe. An Example Paper."),
            line("Example Journal, 2025. doi:10.1234/example.", x=65, top=113),
        ],
        "pdf-ref-0001",
        [],
    )
    fragments = item["pdf"]["fragments"]
    mappings = item["pdf"]["field_evidence"]
    title_spans = [
        fragments[m["fragment"]]["text"][m["start"] : m["end"]] for m in mappings["title"]
    ]
    assert " ".join(title_spans) == "An Example Paper"
    doi_spans = [fragments[m["fragment"]]["text"][m["start"] : m["end"]] for m in mappings["doi"]]
    assert " ".join(doi_spans) == "10.1234/example"


def test_clipped_locator_does_not_invalidate_reliable_title_and_author_fields():
    url = line("https://arxiv.org/abs/2406.12276v1", x=65, top=113)
    url["_clipped"] = True
    item = parse_reference(
        [line("Jane Smith. Example Paper. Example Journal, 2025."), url],
        "pdf-ref-0001",
        [],
    )
    issues = [d for d in item["pdf"]["diagnostics"] if d["code"] == "clipped_text"]
    assert issues
    fields = {field for issue in issues for field in issue["fields"]}
    assert "arxiv" in fields
    assert not fields & {"title", "authors", "year", "journal"}
    assert item["pdf"]["fragments"][1]["clipped"] is True
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_clipped_prose_marks_only_fields_supported_by_that_fragment():
    title = line("Jane Smith. Example Paper.")
    title["_clipped"] = True
    item = parse_reference(
        [title, line("Example Journal, 2025.", x=65, top=113)],
        "pdf-ref-0001",
        [],
    )
    fields = {
        field
        for issue in item["pdf"]["diagnostics"]
        if issue["code"] == "clipped_text"
        for field in issue["fields"]
    }
    assert fields == {"title", "authors"}


def test_inverted_full_given_names_keep_commas_inside_each_person():
    item = citation(
        "Smith, Jane and van der Waals, Johannes. Example Paper. Example Journal, 2025."
    )
    first, second = item["entry"]["persons"]["author"]
    assert first["first"] == ["Jane"] and first["last"] == ["Smith"]
    assert second["first"] == ["Johannes"]
    assert second["prelast"] == ["van", "der"] and second["last"] == ["Waals"]


def test_unknown_work_type_is_not_invented_as_a_journal_article():
    item = citation("Jane Smith. Example Paper. 2025.")
    assert item["entry"]["type"] == "misc"


def test_bare_arxiv_locator_remains_routable_with_its_version_pin():
    from bib_lint.verification.matching import input_record

    item = citation("Jane Smith. Example Paper. arXiv:2406.12276v1, 2025.")
    assert input_record(item["entry"])["identifiers"]["arxiv"] == "2406.12276v1"
    assert item["entry"]["fields"]["eprint"] == "2406.12276v1"


def test_balanced_parentheses_inside_doi_are_retained():
    item = citation(
        "Jane Smith. Example Paper. Example Journal, 2025. doi:10.1234/example(supplement)."
    )
    assert item["entry"]["fields"]["doi"] == "10.1234/example(supplement)"


def test_arxiv_identifier_digits_are_not_a_publication_year_when_year_is_missing():
    item = citation("Jane Smith. Example Paper. arXiv:2001.12345v1.")
    assert "year" not in item["entry"]["fields"]
    assert any(d["code"] == "missing_year" for d in item["pdf"]["diagnostics"])


def test_conference_name_year_does_not_fill_a_missing_citation_year():
    item = citation(
        "Jane Smith. Example Paper. In Proceedings of the 2025 Conference on Language Models."
    )
    assert "year" not in item["entry"]["fields"]
    assert "2025" in item["entry"]["fields"]["journal"]


def test_missing_title_url_is_not_promoted_to_a_title_and_printed_year_is_kept():
    item = citation("Jane Smith. 2025. https://arxiv.org/abs/2406.12276v1.")
    assert "title" not in item["entry"]["fields"]
    assert item["entry"]["fields"]["year"] == "2025"
    assert any(d["code"] == "missing_title" for d in item["pdf"]["diagnostics"])


def test_missing_title_journal_is_not_promoted_to_a_paper_title():
    item = citation("Jane Smith. Journal of Example Research, 12(3):1-8, 2025.")
    assert "title" not in item["entry"]["fields"]
    assert item["entry"]["fields"]["journal"] == "Journal of Example Research"
    assert item["entry"]["fields"]["year"] == "2025"


def test_unparseable_author_punctuation_keeps_the_reference_for_review():
    item = citation("Smith, J., III, IV. Example Paper. Example Journal, 2025.")
    assert item["pdf"]["text"].startswith("Smith, J., III, IV.")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert item["validations"]["extraction"]["state"] == "needs_review"
    assert any("authors" in issue["fields"] for issue in item["pdf"]["diagnostics"])


def test_full_given_name_list_with_a_middle_initial_is_not_an_inverted_single_author():
    item = citation(
        "Daya Guo, Dejian Yang, J. Q. Smith, Haowei Zhang, Junxiao Song, and Xingkai Yu. "
        "Example Paper. Example Journal, 2025."
    )
    names = item["entry"]["persons"]["author"]
    assert [person["last"] for person in names] == [
        ["Guo"],
        ["Yang"],
        ["Smith"],
        ["Zhang"],
        ["Song"],
        ["Yu"],
    ]
    assert names[2]["first"] == ["J."] and names[2]["middle"] == ["Q."]


def test_comma_delimited_citation_year_is_not_part_of_the_title():
    item = citation("Jane Smith. Example Paper, 2025a. https://arxiv.org/abs/2406.12276v1.")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert item["entry"]["fields"]["year"] == "2025"


def test_inverted_initials_end_at_the_title_instead_of_consuming_it():
    item = citation(
        "Gupta, T., Weihs, L., and Kembhavi, A. A paper about agents, 2024. "
        "https://arxiv.org/abs/2406.12276v1."
    )
    assert item["entry"]["fields"]["title"] == "A paper about agents"
    assert [p["last"] for p in item["entry"]["persons"]["author"]] == [
        ["Gupta"],
        ["Weihs"],
        ["Kembhavi"],
    ]
    assert [p["first"] for p in item["entry"]["persons"]["author"]] == [["T."], ["L."], ["A."]]


def test_initial_author_followed_by_others_preserves_the_truncation_marker():
    item = citation("Gupta, T. others. Example Paper, 2024.")
    people = item["entry"]["persons"]["author"]
    assert len(people) == 2
    assert people[0]["first"] == ["T."] and people[0]["last"] == ["Gupta"]
    assert people[1]["kind"] == "others"
    assert item["entry"]["fields"]["title"] == "Example Paper"


def test_line_break_hyphen_is_joined_without_inventing_a_word_boundary():
    item = parse_reference(
        [
            line("Jane Smith. Reliable rein-"),
            line("forcement learning. Example Journal, 2025.", x=65, top=113),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["title"] == "Reliable rein-forcement learning"
    assert item["pdf"]["fragments"][0]["text"].endswith("rein-")
    assert item["pdf"]["fragments"][1]["text"].startswith("forcement")


def test_family_name_hyphen_at_a_line_break_does_not_create_a_new_name_part():
    item = parse_reference(
        [line("Anssi Kan-"), line("ervisto. Example Paper. Example Journal, 2025.", x=65, top=113)],
        "pdf-ref-0001",
        [],
    )
    name = item["entry"]["persons"]["author"][0]
    assert name["first"] == ["Anssi"]
    assert name["middle"] == []
    assert name["last"] == ["Kan-ervisto"]


def test_adjacent_legacy_pdf_accent_is_composed_without_losing_original_glyphs():
    item = citation(
        "Gre´goire Mialon and Cle´mentine Fourrier. E´valuation of agents. Journal, 2025."
    )
    first, second = item["entry"]["persons"]["author"]
    assert first["first"] == ["Grégoire"]
    assert second["first"] == ["Clémentine"]
    assert item["entry"]["fields"]["title"] == "Évaluation of agents"
    assert "Gre´goire" in item["pdf"]["fragments"][0]["text"]
    assert "E´valuation" in item["pdf"]["fragments"][0]["text"]


def test_spacing_accent_with_a_gap_remains_uncertain_instead_of_being_guessed():
    item = citation("Gre ´goire Mialon. Example Paper. Journal, 2025.")
    assert any(
        issue["code"] == "ambiguous_diacritic" and "authors" in issue["fields"]
        for issue in item["pdf"]["diagnostics"]
    )
    assert "Gre ´goire" in item["pdf"]["fragments"][0]["text"]


def test_apostrophes_and_actual_different_names_are_not_removed_as_accents():
    item = citation("Jane O'Connor and Gregoire Mialon. Example Paper. Journal, 2025.")
    first, second = item["entry"]["persons"]["author"]
    assert first["last"] == ["O'Connor"]
    assert second["first"] == ["Gregoire"]


def test_incomplete_initial_author_at_end_is_retained_without_parser_crash():
    item = citation("Gupta, T. ")
    assert item["pdf"]["fragments"][0]["text"] == "Gupta, T. "
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_multiple_and_hyphenated_initials_do_not_terminate_author_block():
    item = citation("Liang, J. H. a. P. and Kwon, Y.-D. Example Paper, 2025.")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    people = item["entry"]["persons"]["author"]
    assert people[0]["first"] == ["J."]
    assert people[0]["middle"] == ["H.", "a.", "P."]
    assert people[1]["first"] == ["Y.-D."]


def test_given_initial_with_trailing_comma_still_belongs_to_same_author():
    item = citation("Gelman, A., Carlin, J. B., and Stern, H. S. Bayesian Data Analysis, 2013.")
    assert item["entry"]["fields"]["title"] == "Bayesian Data Analysis"
    people = item["entry"]["persons"]["author"]
    assert people[1]["first"] == ["J."] and people[1]["middle"] == ["B."]


def test_inverted_and_normal_suffixes_preserve_the_same_structured_lineage():
    inverted = citation("Gupta, Jr., T., Weihs, L., and Kembhavi, A. Example Paper, 2024.")
    normal = citation("Tanmay Gupta, Jr., Luca Weihs, and Aniruddha Kembhavi. Example Paper, 2024.")
    assert (
        inverted["entry"]["fields"]["title"]
        == normal["entry"]["fields"]["title"]
        == "Example Paper"
    )
    for item in (inverted, normal):
        people = item["entry"]["persons"]["author"]
        assert len(people) == 3
        assert people[0]["last"] == ["Gupta"]
        assert people[0]["lineage"] == ["Jr."]


def test_legitimate_surname_an_in_a_long_author_list_is_not_an_article_word():
    item = citation("Daya Guo, Wei An, and Zhen Zhang. Example Paper. Journal, 2025.")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert [p["last"] for p in item["entry"]["persons"]["author"]] == [["Guo"], ["An"], ["Zhang"]]


def test_semicolon_author_list_does_not_treat_and_as_a_surname_particle():
    item = citation("Gupta, T.; Weihs, L.; and Kembhavi, A. 2024. Example Paper.")
    people = item["entry"]["persons"]["author"]
    assert len(people) == 3
    assert people[-1]["prelast"] == [] and people[-1]["last"] == ["Kembhavi"]


def test_year_only_prefix_is_a_date_and_never_a_placeholder_person():
    item = citation("2025. Measuring AI Ability to Complete Long Tasks. METR Blog.")
    assert item["entry"]["fields"]["year"] == "2025"
    assert item["entry"]["fields"]["title"] == "Measuring AI Ability to Complete Long Tasks"
    assert not item["entry"]["persons"].get("author")


def test_colon_after_a_final_unabbreviated_surname_is_an_author_boundary():
    item = citation("Smith, J., Doe: Example Paper. In: A Conference (2024).")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert item["entry"]["fields"]["year"] == "2024"


def test_parenthesized_citation_date_and_url_are_not_part_of_the_title():
    item = citation("Smith, J.: Example Paper (2024), https://arxiv.org/abs/2406.12276v1")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert item["entry"]["fields"]["year"] == "2024"


def test_visual_space_after_url_scheme_is_retained_as_evidence_and_parsed_locally():
    item = citation("Jane Smith. Example Paper (2025), https: //arxiv.org/abs/2406.12276v1")
    assert item["entry"]["fields"]["title"] == "Example Paper"
    assert item["entry"]["fields"]["url"] == "https://arxiv.org/abs/2406.12276v1"
    assert item["entry"]["fields"]["year"] == "2025"
    assert "https: //" in item["pdf"]["fragments"][0]["text"]


def test_semicolon_style_author_year_boundary_precedes_a_title_colon():
    item = citation("Gupta, T.; Weihs, L.; and Kembhavi, A. 2024. CodeNav: Beyond tool-use.")
    assert item["entry"]["fields"]["title"] == "CodeNav: Beyond tool-use"
    assert [p["last"] for p in item["entry"]["persons"]["author"]] == [
        ["Gupta"],
        ["Weihs"],
        ["Kembhavi"],
    ]


@pytest.mark.parametrize("authors", ["others", "Tanmay Gupta, et al."])
def test_colon_style_truncation_prefix_does_not_become_part_of_the_title(authors):
    item = citation(f"{authors}: CodeNav: Beyond tool-use (2024).")
    assert item["entry"]["fields"]["title"] == "CodeNav: Beyond tool-use"
    assert item["entry"]["persons"]["author"][-1]["kind"] == "others"


@pytest.mark.parametrize("placeholder", ["???", "????a", "????b"])
def test_typesetter_unknown_year_placeholder_is_not_a_paper_title(placeholder):
    item = citation(f"Gupta, T. {placeholder}. CodeNav: Beyond tool-use. arXiv:2406.12276v1.")
    assert item["entry"]["fields"]["title"] == "CodeNav: Beyond tool-use"
    assert "year" not in item["entry"]["fields"]
    assert any(issue["code"] == "missing_year" for issue in item["pdf"]["diagnostics"])


def test_typesetter_empty_reference_placeholder_does_not_invent_metadata():
    item = citation("????")
    assert item["entry"]["fields"] == {}
    assert item["entry"]["persons"] == {}
    assert item["pdf"]["text"] == "????"
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_explicit_malformed_doi_is_preserved_for_existing_locator_checks():
    item = citation("Jane Smith. Example Paper. Journal, 2025. doi:10.123/example.")
    assert item["entry"]["fields"]["doi"] == "10.123/example"
    assert item["pdf"]["field_evidence"]["doi"]


def test_explicit_legacy_arxiv_locator_preserves_its_version_pin():
    item = citation("Jane Smith. Example Paper. Journal, 2006. arXiv:cs/0601001v2.")
    assert item["entry"]["fields"]["arxiv"] == "cs/0601001v2"
    assert item["entry"]["fields"]["eprint"] == "cs/0601001v2"


def test_unquoted_multisentence_title_without_typographic_boundary_needs_review():
    item = citation(
        "Jane Smith. A Comprehensive Study of Attention Networks. Why? Journal, 2025. "
        "doi:10.1234/example."
    )
    issues = [
        issue for issue in item["pdf"]["diagnostics"] if issue["code"] == "ambiguous_boundary"
    ]
    assert issues
    assert {"title", "venue"} <= {field for issue in issues for field in issue["fields"]}
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_distinct_italic_venue_proves_where_a_multisentence_title_ends():
    text = "Jane Smith. A Comprehensive Study of Attention Networks. Why? Journal, 2025."
    fragment = line(text)
    start = text.index("Journal")
    fragment["_spans"] = [
        {"start": 0, "end": start, "font": "Times-Roman", "size": 10},
        {"start": start, "end": start + len("Journal"), "font": "Times-Italic", "size": 10},
    ]
    item = parse_reference([fragment], "pdf-ref-0001", [])
    assert item["entry"]["fields"]["title"] == "A Comprehensive Study of Attention Networks. Why?"
    assert item["entry"]["fields"]["journal"] == "Journal"
    assert not any(d["code"] == "ambiguous_boundary" for d in item["pdf"]["diagnostics"])


def test_wrapped_arxiv_decimal_identifier_joins_a_numeric_continuation():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2024."),
            line("URL https://arxiv.org/abs/2406.", x=65, top=113),
            line("12276v1.", x=65, top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["url"] == "https://arxiv.org/abs/2406.12276v1"
    assert not any(d["code"] == "locator_conflict" for d in item["pdf"]["diagnostics"])


def test_wrapped_doi_year_dot_joins_hyphenated_suffix():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025."),
            line("doi:10.18653/v1/2025.", x=65, top=113),
            line("emnlp-main.58.", x=65, top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["doi"] == "10.18653/v1/2025.emnlp-main.58"


def test_single_footer_digit_is_not_glued_to_a_terminal_url_period():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025."),
            line("https://example.org/paper.", x=65, top=113),
            line("4", x=65, top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["url"] == "https://example.org/paper"


@pytest.mark.parametrize("label,field", [("doi", "doi"), ("arXiv", "arxiv")])
def test_explicit_punctuation_only_locator_is_not_silently_erased(label, field):
    item = citation(f"Jane Smith. Example Paper. Journal, 2025. {label}:.")
    assert item["entry"]["fields"][field] == "."
    assert item["pdf"]["field_evidence"][field]


@pytest.mark.parametrize("label,field", [("doi", "doi"), ("arXiv", "arxiv")])
def test_empty_explicit_locator_label_requires_review_without_placeholder_values(label, field):
    item = citation(f"Jane Smith. Example Paper. Journal, 2025. {label}:")
    assert field not in item["entry"]["fields"]
    assert any(field in d["fields"] for d in item["pdf"]["diagnostics"])
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_malformed_secondary_doi_annotation_cannot_hide_behind_correct_printed_doi():
    uri = {
        "uri": "https://doi.org/https://doi.org/10.1234/example",
        "page": 1,
        "x0": 50,
        "top": 100,
        "x1": 550,
        "bottom": 110,
    }
    item = parse_reference(
        [line("Jane Smith. Example Paper. Journal, 2025. doi:10.1234/example.")],
        "pdf-ref-0001",
        [uri],
    )
    assert item["entry"]["fields"]["doi"] == "10.1234/example"
    assert item["pdf"]["uris"][0] == uri
    assert any("doi" in issue["fields"] for issue in item["pdf"]["diagnostics"])
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_annotation_target_terminal_punctuation_is_not_erased_as_prose():
    uri = {
        "uri": "https://arxiv.org/abs/2406.12276v1.",
        "page": 1,
        "x0": 50,
        "top": 100,
        "x1": 550,
        "bottom": 110,
    }
    item = parse_reference(
        [line("Jane Smith. Example Paper. Journal, 2024. https://arxiv.org/abs/2406.12276v1.")],
        "pdf-ref-0001",
        [uri],
    )
    assert item["pdf"]["uris"][0]["uri"].endswith("v1.")
    assert any("arxiv" in issue["fields"] for issue in item["pdf"]["diagnostics"])


@pytest.mark.parametrize("continuation", ["Why?.", "Part II."])
def test_unquoted_additional_title_sentence_is_not_a_reliable_venue(continuation):
    item = citation(
        f"Jane Smith. A Comprehensive Study of Attention Networks. {continuation} Journal, 2025."
    )
    assert any(d["code"] == "ambiguous_boundary" for d in item["pdf"]["diagnostics"])
    assert item["validations"]["extraction"]["state"] == "needs_review"


def test_native_journal_pagination_is_not_part_of_the_venue():
    item = citation("Jane Smith. Example Paper. Journal of Example Research, (268):1–8, 2025.")
    assert item["entry"]["fields"]["journal"] == "Journal of Example Research"


def test_standalone_publication_year_suffix_does_not_invent_a_venue():
    item = citation("Jane Smith. Example Paper. 2025f.")
    assert item["entry"]["fields"]["year"] == "2025"
    assert "journal" not in item["entry"]["fields"]


def test_printed_volume_is_routing_context_with_precise_original_evidence():
    item = citation("Jane Smith. Example Paper. Journal of Example Research, 22(268):1–8, 2031.")
    assert item["entry"]["fields"]["journal"] == "Journal of Example Research"
    assert item["entry"]["fields"]["volume"] == "22"
    assert item["entry"]["fields"]["year"] == "2031"
    evidence = item["pdf"]["field_evidence"]["volume"]
    assert (
        "".join(
            item["pdf"]["fragments"][m["fragment"]]["text"][m["start"] : m["end"]] for m in evidence
        )
        == "22"
    )


def test_typesetter_counted_author_truncation_is_an_others_sentinel():
    item = citation("Jane Smith, John Brown, and 175 others. 2025. Example Paper. Journal.")
    names = item["entry"]["persons"]["author"]
    assert len(names) == 3
    assert names[-1]["kind"] == "others"
    assert names[-1]["last"] == ["others"]


def test_counted_author_truncation_across_a_discretionary_hyphen_is_preserved():
    item = parse_reference(
        [
            line("Jane Smith, John Brown, and 175 oth-"),
            line("ers. 2025. Example Paper. Journal.", top=113),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["persons"]["author"][-1]["kind"] == "others"
    assert item["entry"]["fields"]["title"] == "Example Paper"


def test_book_edition_is_separate_printed_context_and_not_part_of_title():
    item = citation("Jane Smith. 2013. Bayesian Data Analysis, 3rd edition. Example Publisher.")
    assert item["entry"]["fields"]["title"] == "Bayesian Data Analysis"
    assert item["entry"]["fields"]["edition"] == "3rd"
    assert item["pdf"]["field_evidence"]["edition"]


def test_preprint_locator_cannot_be_promoted_into_a_missing_title():
    item = citation("Jane Smith. 2024. Preprint, arXiv:2406.12276v1.")
    assert "title" not in item["entry"]["fields"]
    assert any(d["code"] == "missing_title" for d in item["pdf"]["diagnostics"])


@pytest.mark.parametrize(
    "prefix,continuation,expected",
    [
        (
            r"HTTPS://doi.org/10.18653\%2Fv1\%2F2025.",
            "EMNLP-MAIN.58.",
            r"HTTPS://doi.org/10.18653\%2Fv1\%2F2025.EMNLP-MAIN.58",
        ),
        (
            "HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.",
            "58.",
            "HTTPS://doi.org/10.18653%2Fv1%2F2025.EMNLP-MAIN.58",
        ),
    ],
)
def test_wrapped_doi_retains_uppercase_encoded_and_short_numeric_suffix(
    prefix, continuation, expected
):
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025."),
            line("doi: " + prefix, top=113),
            line(continuation + " URL https://example.org/paper.", top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["doi"] == expected
    assert item["pdf"]["field_evidence"]["doi"][-1]["fragment"] == 2


def test_journal_comma_volume_comma_year_retains_routing_context():
    item = citation("Jane Smith. Example Paper. Journal of Example Research, 22, 2031.")
    assert item["entry"]["fields"]["volume"] == "22"
    assert item["entry"]["fields"]["year"] == "2031"
    mappings = item["pdf"]["field_evidence"]["volume"]
    assert (
        "".join(
            item["pdf"]["fragments"][m["fragment"]]["text"][m["start"] : m["end"]] for m in mappings
        )
        == "22"
    )


def test_explicit_foreign_arxiv_wrapper_is_preserved_as_invalid_identifier_evidence():
    item = citation("Jane Smith. 2024. Example Paper. arXiv:https://evil.example/2406.12276v1.")
    assert item["entry"]["fields"]["arxiv"] == "https://evil.example/2406.12276v1"
    assert item["entry"]["fields"]["eprint"] == "https://evil.example/2406.12276v1"
    assert any(
        d["code"] == "malformed_locator" and d["fields"] == ["arxiv"]
        for d in item["pdf"]["diagnostics"]
    )


def test_terminal_doi_followed_by_new_author_sentence_is_not_joined():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025. doi:10.1234/example."),
            line("Nathan Lambert. Another Paper.", top=113),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["doi"] == "10.1234/example"


def test_wrapped_url_extension_followed_by_a_comma_is_retained():
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025."),
            line("URL https://proceedings.mlr.press/v70/shi17a.", top=113),
            line("html, bibTeX Type: inproceedings BibTeX Key: example.", top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["url"] == "https://proceedings.mlr.press/v70/shi17a.html"
    evidence = item["pdf"]["field_evidence"]["url"]
    assert any(m["fragment"] == 2 for m in evidence)


@pytest.mark.parametrize("suffix", ["48550/arXiv.2211.10435.", "52202/075280-1723."])
def test_bare_doi_decimal_prefix_line_wrap_is_retained(suffix):
    item = parse_reference(
        [
            line("Jane Smith. Example Paper. Journal, 2025. doi: 10."),
            line(suffix, top=113),
        ],
        "pdf-ref-0001",
        [],
    )
    assert item["entry"]["fields"]["doi"] == "10." + suffix.rstrip(".")
    assert not any(d["code"] == "malformed_locator" for d in item["pdf"]["diagnostics"])


def test_terminal_journal_volume_is_retained_when_publication_year_precedes_title():
    item = citation("Jane Smith. 2031. Example Paper. Journal of Example Research, 22.")
    assert item["entry"]["fields"]["volume"] == "22"
    assert item["entry"]["fields"]["year"] == "2031"
    evidence = item["pdf"]["field_evidence"]["volume"]
    assert (
        "".join(
            item["pdf"]["fragments"][m["fragment"]]["text"][m["start"] : m["end"]] for m in evidence
        )
        == "22"
    )


def test_terminal_journal_publication_year_is_not_invented_as_volume():
    item = citation("Jane Smith. Example Paper. Journal of Example Research, 2025.")
    assert item["entry"]["fields"]["year"] == "2025"
    assert "volume" not in item["entry"]["fields"]


def test_generic_italic_preprint_status_is_not_a_publication_venue():
    from bib_lint.verification.matching import input_record

    item = parse_reference(
        [
            line("Jane Smith. 2024. Example Paper."),
            line("Preprint", font="Times-Italic", top=113),
            line(", arXiv:2406.12276v1.", top=126),
        ],
        "pdf-ref-0001",
        [],
    )
    assert "journal" not in item["entry"]["fields"]
    assert "Preprint" in item["pdf"]["text"]
    assert input_record(item["entry"])["record_type"] == "preprint"


@pytest.mark.parametrize("authors", ["others", "et al."])
def test_only_truncation_sentinel_retains_evidence_but_named_authors_are_unknown(authors):
    item = citation(f"{authors}. 2024. Example Paper. Journal.")
    assert item["entry"]["persons"]["author"][0]["kind"] == "others"
    assert authors in item["pdf"]["text"]
    assert any(
        d["code"] == "missing_authors" and d["fields"] == ["authors"]
        for d in item["pdf"]["diagnostics"]
    )
    assert item["validations"]["extraction"]["state"] == "needs_review"
