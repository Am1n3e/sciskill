"""Layout regressions isolated from citation identities and conference names."""

from bib_lint.pdf_input.layout import _line_numbers, bibliography_lines


def word(text, x, top, *, font="Times-Roman", size=10):
    return {
        "text": text,
        "x0": x,
        "x1": x + len(text) * size / 2,
        "top": top,
        "bottom": top + size,
        "fontname": font,
        "size": size,
    }


def test_line_number_style_removes_isolated_gutter_continuations():
    styles = set()
    words = [word(str(i), 30, 100 + i * 13, font="Helvetica", size=6) for i in range(8)]
    words += [
        word("ordinary", 60, 100),
        word("text", 110, 100),
        word("38", 301, 300, font="Helvetica", size=6),
        word("2024", 180, 200),
    ]
    result = _line_numbers(words, styles)
    assert [w["text"] for w in result] == ["ordinary", "text", "2024"]
    short_page = [word(str(i), 30, 100 + i, font="Helvetica", size=6) for i in range(100, 103)]
    short_page.append(word("continued", 60, 100))
    assert [w["text"] for w in _line_numbers(short_page, styles)] == ["continued"]


def test_aligned_publication_years_are_not_review_line_numbers():
    words = [word(str(year), 200, 100 + i * 15) for i, year in enumerate(range(2023, 2027))]
    words += [word("Smith", 50, 100), word("Journal", 100, 100)]
    assert _line_numbers(words, set()) == words


def test_running_review_header_with_punctuation_is_not_reference_text():
    def row(text, x, top, column=0):
        return {
            "text": text,
            "page": 2,
            "x0": x,
            "x1": x + len(text) * 3,
            "top": top,
            "bottom": top + 10,
            "_column": column,
            "_width": 612,
            "_spans": [{"font": "Times-Roman", "start": 0, "end": len(text), "size": 10}],
        }

    pages = [
        [row("References", 50, 100), row("[1] Jane Smith. Example Paper. 2024.", 50, 130)],
        [
            row("CONFIDENTIAL REVIEW COPY.", 140, 35),
            row("DO NOT DISTRIBUTE.", 320, 35, 1),
            row("Continuation of the reference.", 65, 100),
        ],
    ]
    selected, _ = bibliography_lines(pages)
    assert not any(
        "CONFIDENTIAL" in line["text"] or "DISTRIBUTE" in line["text"] for line in selected
    )


def test_line_numbers_can_share_the_body_font_without_removing_publication_years():
    styles = set()
    numbers = [word(str(i), 40 - len(str(i)) * 5, 100 + i * 13) for i in range(8)]
    body = [word("ordinary", 60, 100), word("text", 110, 100), word("2024", 180, 200)]
    assert _line_numbers(numbers + body, styles) == body
    continued = [word("100", 25, 100), word("continued", 60, 100), word("2025", 180, 200)]
    assert _line_numbers(continued, styles) == continued[1:]
