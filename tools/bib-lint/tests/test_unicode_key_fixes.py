"""One exact-first policy for key selection, AUX usage, and missing-key warnings."""

import json

import pytest

from bib_lint.audit import prepare_input, run_audit
from bib_lint.parser import BibliographyParseError, parse_file, parse_string
from bib_lint.scope import selected_items, validate_report
from bib_lint.workflow import parse_bib

PAIR = ("alias_ſb3", "alias_sb3")


def inputs(tmp_path, keys, citations=None):
    bib = tmp_path / "references.bib"
    bib.write_text("\n".join("@book{" + key + ",title={A reference}}" for key in keys))
    aux = tmp_path / "paper.aux"
    if citations is not None:
        aux.write_text("\\citation{" + ",".join(citations) + "}\n")
    return bib, aux


def used_keys(report):
    return [item["entry"]["key"] for item in report["items"] if item["validations"]["is_used"]]


def test_exact_key_selection_preserves_distinct_unicode_aliases(tmp_path):
    bib, _ = inputs(tmp_path, PAIR)
    report, _, _ = prepare_input(bib)
    assert [i["entry"]["key"] for i in report["items"]] == list(PAIR)
    for key in PAIR:
        assert [i["entry"]["key"] for i in selected_items(report, key)] == [key]


def test_unique_unicode_casefold_selection(tmp_path):
    bib, _ = inputs(tmp_path, ["alias_ſingle"])
    report, _, _ = prepare_input(bib)
    assert selected_items(report, "ALIAS_SINGLE")[0]["entry"]["key"] == "alias_ſingle"


def test_ambiguous_alias_selection_preserves_checkpoint(tmp_path):
    bib, _ = inputs(tmp_path, PAIR)
    output = tmp_path / "audit"
    workspace, _, _ = run_audit(bib, output=output, preview=True)
    before = workspace.checkpoint.read_bytes()
    with pytest.raises(ValueError, match="Ambiguous citation key"):
        run_audit(bib, output=output, citation_key="ALIAS_SB3", preview=True)
    assert workspace.checkpoint.read_bytes() == before


@pytest.mark.parametrize("key", PAIR)
def test_exact_aux_key_selects_only_its_own_unicode_identity(tmp_path, key):
    bib, aux = inputs(tmp_path, PAIR, [key])
    report, _, warnings = prepare_input(bib, aux=aux)
    assert used_keys(report) == [key]
    assert warnings == []
    parsed, usage = parse_bib(bib, aux)
    assert parsed.error is usage.error is None
    assert usage.total == 1 and usage.unused == 1 and usage.missing == []
    assert used_keys(json.loads(parsed.output.read_text())) == [key]


@pytest.mark.parametrize("key,alias", [("alias_ſingle", "ALIAS_SINGLE"), ("Straße", "STRASSE")])
def test_aux_alias_usage_and_warnings_share_unicode_resolution(tmp_path, key, alias):
    bib, aux = inputs(tmp_path, [key, "unused"], [alias, "missing"])
    before = bib.read_bytes(), aux.read_bytes()
    assert used_keys(parse_file(bib).to_dict(used_keys={alias})) == [key]
    report, _, warnings = prepare_input(bib, aux=aux)
    assert used_keys(report) == [key]
    assert report["verification_scope"]["eligible_keys"] == [key]
    assert warnings == ["Missing citation keys: missing"]
    parsed, usage = parse_bib(bib, aux)
    assert parsed.error is usage.error is None
    assert usage.total == 2 and usage.unused == 1 and usage.missing == ["missing"]
    assert used_keys(json.loads(parsed.output.read_text())) == [key]
    assert (bib.read_bytes(), aux.read_bytes()) == before


def test_ambiguous_aux_alias_fails_before_any_output_replacement(tmp_path):
    bib, aux = inputs(tmp_path, PAIR, ["ALIAS_SB3"])
    with pytest.raises(ValueError, match="Ambiguous citation key"):
        parse_file(bib).to_dict(used_keys={"ALIAS_SB3"})
    with pytest.raises(ValueError, match="Ambiguous citation key"):
        prepare_input(bib, aux=aux)
    output = tmp_path / "audit"
    with pytest.raises(ValueError, match="Ambiguous citation key"):
        run_audit(bib, aux=aux, output=output, preview=True)
    assert not output.exists()
    previous = tmp_path / "saved.tmp.json"
    previous.write_text('{"previous": true}')
    parsed, usage = parse_bib(bib, aux, output=previous)
    assert parsed.error is None
    assert "Ambiguous citation key" in usage.error
    assert previous.read_text() == '{"previous": true}'


def test_wildcard_and_repeated_unique_aliases_keep_usage_counts(tmp_path):
    bib, aux = inputs(tmp_path, ["alias_ſingle", "unused"], ["alias_ſingle", "ALIAS_SINGLE"])
    parsed, usage = parse_bib(bib, aux)
    assert parsed.error is usage.error is None
    assert usage.total == 1 and usage.unused == 1
    assert used_keys(json.loads(parsed.output.read_text())) == ["alias_ſingle"]
    aux.write_text("\\citation{*,ALIAS_SINGLE,missing}\n")
    report, _, warnings = prepare_input(bib, aux=aux)
    assert used_keys(report) == ["alias_ſingle", "unused"]
    assert warnings == ["Missing citation keys: missing"]
    parsed, usage = parse_bib(bib, aux)
    assert usage.total == 2 and usage.unused == 0 and usage.missing == ["missing"]


def test_ascii_case_duplicates_remain_rejected_in_bibtex_and_saved_reports():
    with pytest.raises(BibliographyParseError):
        parse_string("@book{A,title={First}}\n@book{a,title={Second}}")
    report = {
        "schema_version": 2,
        "items": [
            {
                "entry": {"key": key, "fields": {"title": "A reference"}, "persons": {}},
                "validations": {"is_used": True},
            }
            for key in ["A", "a"]
        ],
    }
    with pytest.raises(ValueError, match="Duplicate citation keys"):
        validate_report(report)
