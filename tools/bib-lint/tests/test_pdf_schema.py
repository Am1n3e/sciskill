import copy

import pytest
from pdf_support import pdf_report

from bib_lint.scope import fingerprint, validate_report


def sealed():
    from bib_lint.pdf_evidence import seal_extraction

    report = pdf_report()
    seal_extraction(report)
    return report


def test_pdf_schema_keeps_unknown_usage_and_checks_inline_evidence():
    report = sealed()
    assert validate_report(report) == {"mode": "all", "eligible_keys": ["pdf-ref-0001"]}
    report["items"][0]["pdf"]["fragments"][0]["text"] = "tampered"
    with pytest.raises(ValueError, match="evidence checksum"):
        validate_report(report)


@pytest.mark.parametrize("value", [True, -1, 0, 2, 1.5, float("nan"), "1"])
def test_pdf_fragment_pages_are_physical_integer_pages(value):
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["items"][0]["pdf"]["fragments"][0]["page"] = value
    seal_extraction(report)
    with pytest.raises(ValueError, match="page"):
        validate_report(report)


@pytest.mark.parametrize(
    "field,value", [("x0", -1), ("x1", 700), ("top", float("inf")), ("bottom", "111"), ("x0", True)]
)
def test_pdf_boxes_must_be_finite_inside_the_page(field, value):
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["items"][0]["pdf"]["fragments"][0][field] = value
    seal_extraction(report)
    with pytest.raises(ValueError, match="box"):
        validate_report(report)


@pytest.mark.parametrize(
    "mapping",
    [
        {"fragment": 2, "start": 0, "end": 5},
        {"fragment": 0, "start": -1, "end": 2},
        {"fragment": 0, "start": 4, "end": 1000},
        {"fragment": False, "start": 0, "end": 4},
    ],
)
def test_pdf_fields_require_valid_original_text_spans(mapping):
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["items"][0]["pdf"]["field_evidence"]["title"] = [mapping]
    seal_extraction(report)
    with pytest.raises(ValueError, match="mapping"):
        validate_report(report)


def test_pdf_identity_uses_bytes_parser_settings_and_original_evidence():
    from bib_lint.pdf_evidence import seal_extraction

    original = sealed()
    base = fingerprint(original)
    for key, value in [
        ("document", {**original["extraction"]["document"], "sha256": "b" * 64}),
        ("parser", {"id": "bib-lint-local", "version": "next"}),
        ("settings", {"max_pages": 201}),
    ]:
        changed = copy.deepcopy(original)
        changed["extraction"][key] = value
        seal_extraction(changed)
        assert fingerprint(changed) != base
    renamed = copy.deepcopy(original)
    renamed["extraction"]["document"]["name"] = "renamed.pdf"
    renamed["source"]["name"] = "renamed.pdf"
    seal_extraction(renamed)
    assert fingerprint(renamed) == base


def test_empty_pdf_report_is_not_an_empty_success():
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["items"] = []
    report["verification_scope"]["eligible_keys"] = []
    seal_extraction(report)
    with pytest.raises(ValueError, match="references"):
        validate_report(report)


@pytest.mark.parametrize("field", ["pdf", "entry"])
def test_missing_pdf_evidence_is_a_controlled_schema_error(field):
    report = sealed()
    report["items"][0].pop(field)
    with pytest.raises(ValueError):
        validate_report(report)


def test_pdf_cannot_claim_aux_usage():
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["verification_scope"]["mode"] = "used"
    report["items"][0]["validations"]["is_used"] = True
    seal_extraction(report)
    with pytest.raises(ValueError, match="usage"):
        validate_report(report)


@pytest.mark.parametrize("value", [True, "match", "invalid", None])
def test_pdf_diagnostic_result_has_a_closed_vocabulary(value):
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    diagnostic = {
        "code": "conflict",
        "message": "Printed conflict",
        "fields": ["arxiv"],
        "result": value,
    }
    report["items"][0]["pdf"]["diagnostics"] = [diagnostic]
    report["items"][0]["validations"]["extraction"] = {
        "state": "needs_review",
        "diagnostics": [diagnostic],
    }
    seal_extraction(report)
    with pytest.raises(ValueError, match="diagnostic result"):
        validate_report(report)


@pytest.mark.parametrize("pages", [[{}], [None], [1, "2"]])
def test_invalid_reference_page_lists_fail_with_a_controlled_schema_error(pages):
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["extraction"]["reference_pages"] = pages
    seal_extraction(report)
    with pytest.raises(ValueError, match="page"):
        validate_report(report)


def test_pdf_report_schema_version_is_an_integer():
    report = sealed()
    report["schema_version"] = 4.0
    with pytest.raises(ValueError, match="schema"):
        validate_report(report)


@pytest.mark.parametrize("value", [[], None, "all", 1])
def test_pdf_scope_malformed_types_are_controlled(value):
    report = sealed()
    report["verification_scope"] = value
    with pytest.raises(ValueError, match="scope"):
        validate_report(report)


def test_pdf_huge_integer_coordinates_are_controlled():
    from bib_lint.pdf_evidence import seal_extraction

    report = sealed()
    report["items"][0]["pdf"]["fragments"][0]["x0"] = 2**10000
    seal_extraction(report)
    with pytest.raises(ValueError, match="box"):
        validate_report(report)
