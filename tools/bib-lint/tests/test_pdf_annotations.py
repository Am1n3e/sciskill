"""PDF link rectangles must belong to the printed reference they cover."""

from bib_lint.pdf_input.worker import _uris


def test_link_padding_does_not_attach_the_previous_reference_uri_to_the_next_line():
    line = {"page": 3, "x0": 34, "x1": 380, "top": 57.896, "bottom": 66.862}
    previous = {
        "page": 3,
        "x0": 109,
        "x1": 271,
        "top": 47.218,
        "bottom": 58.174,
        "uri": "https://arxiv.org/abs/2406.12276v1",
    }
    assert _uris([line], [previous]) == []


def test_actual_wrong_uri_target_is_retained_when_its_rectangle_covers_the_reference():
    line = {"page": 3, "x0": 34, "x1": 380, "top": 57.896, "bottom": 66.862}
    wrong = {
        "page": 3,
        "x0": 109,
        "x1": 271,
        "top": 57.218,
        "bottom": 68.174,
        "uri": "https://arxiv.org/abs/2406.12276v1",
    }
    assert _uris([line], [wrong]) == [wrong]


def test_zero_area_and_other_page_annotations_are_not_reference_evidence():
    line = {"page": 3, "x0": 34, "x1": 380, "top": 57, "bottom": 67}
    uri = {"page": 3, "x0": 109, "x1": 271, "top": 57, "bottom": 57, "uri": "https://example.org"}
    other = {**uri, "page": 2, "bottom": 67}
    assert _uris([line], [uri, other]) == []
