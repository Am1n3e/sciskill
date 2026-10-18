import pytest

from bib_lint.status import FIELD_LABELS, SOURCE_LABELS, STATUS_COLORS, reference_status
from bib_lint.verification import _totals


@pytest.mark.parametrize(
    ("validations", "expected"),
    [
        ({}, "Pending"),
        ({"is_used": None}, "Pending"),
        ({"is_used": False, "correctness": {"is_correct": True}}, "Skipped"),
        ({"is_used": False}, "Skipped"),
        ({"is_used": True}, "Pending"),
        ({"is_used": True, "correctness": {"is_correct": True, "complete": False}}, "Pending"),
        ({"correctness": {"is_correct": True, "complete": True}}, "Correct"),
        ({"correctness": {"is_correct": False, "complete": True}}, "Invalid"),
        ({"correctness": {"is_correct": None, "complete": True}}, "Unresolved"),
    ],
)
def test_reference_status(validations, expected):
    assert reference_status(validations) == expected


def test_all_source_and_field_states_have_colors():
    assert all(label in STATUS_COLORS for label in SOURCE_LABELS.values())
    assert all(label in STATUS_COLORS for label in FIELD_LABELS.values())
    assert STATUS_COLORS[SOURCE_LABELS["error"]] == "red"
    assert STATUS_COLORS[SOURCE_LABELS["not_applicable"]] == "gray"
    assert STATUS_COLORS[FIELD_LABELS["match"]] == "green"


def test_partial_check_is_not_counted_as_completed_unresolved():
    report = {
        "items": [
            {
                "validations": {
                    "is_used": True,
                    "correctness": {"complete": False, "is_correct": None, "methods": []},
                }
            }
        ]
    }
    assert _totals(report)["unresolved"] == 0
