import json

import pytest

from bib_lint import parse_bib


def setup_inputs(tmp_path, text):
    bib = tmp_path / "refs.bib"
    aux = tmp_path / "paper.aux"
    bib.write_text("@book{Used,title={A}}\n@book{Unused,title={B}}")
    aux.write_text(text)
    return bib, aux


def test_combined_output_and_summary(tmp_path, capsys):
    bib, aux = setup_inputs(
        tmp_path, "\\citation{Used, missing}\n\\citation{Used}\n\\bibcite{Unused}{1}\n"
    )
    first, second = parse_bib(bib, aux)
    assert first.error is second.error is None
    report = json.loads(bib.with_suffix(".tmp.json").read_text())
    assert report["summary"] == {"total_count": 2, "total_not_used": 1}
    assert [item["validations"] for item in report["items"]] == [
        {"is_used": True},
        {"is_used": False},
    ]
    assert report["items"][0]["entry"]["fields"]["title"] == "A"
    assert list(tmp_path.glob("*.json")) == [bib.with_suffix(".tmp.json")]
    assert second.unused == 1
    assert second.missing == ["missing"]


def test_nested_inputs_cycles_comments_and_case(tmp_path):
    bib, aux = setup_inputs(tmp_path, "% \\citation{Unused}\n\\@input{child.aux}\n")
    (tmp_path / "child.aux").write_text("\\citation{used, used}\n\\@input{paper.aux}\n")
    first, second = parse_bib(bib, aux)
    assert first.error is second.error is None
    assert second.total == 1
    assert second.unused == 1


@pytest.mark.parametrize("text, unused", [("\\citation{*}\n", 0), ("\\relax\n", 2)])
def test_all_or_no_citations(tmp_path, text, unused):
    bib, aux = setup_inputs(tmp_path, text)
    first, second = parse_bib(bib, aux)
    assert second.unused == unused
    report = json.loads(first.output.read_text())
    assert report["summary"]["total_not_used"] == unused
    assert all(item["validations"]["is_used"] == (unused == 0) for item in report["items"])


@pytest.mark.parametrize(
    "text",
    [
        "\\@input{missing.aux}",
        "\\citation{broken",
        "\\abx@aux@cite{0}{key}",
    ],
)
def test_aux_failure_preserves_previous_report(tmp_path, text):
    bib, aux = setup_inputs(tmp_path, text)
    output = bib.with_suffix(".tmp.json")
    output.write_text('{"previous": true}')
    first, second = parse_bib(bib, aux)
    assert first.error is None
    assert second.error
    assert output.read_text() == '{"previous": true}'


def test_missing_aux_does_not_write_partial_report(tmp_path, capsys):
    bib, aux = setup_inputs(tmp_path, "")
    aux.unlink()
    assert parse_bib(bib, aux)[1].error
    assert not bib.with_suffix(".tmp.json").exists()


def test_output_cannot_overwrite_included_aux(tmp_path):
    bib, aux = setup_inputs(tmp_path, "\\@input{child.aux}")
    child = tmp_path / "child.aux"
    child.write_text("\\citation{Used}")
    _, second = parse_bib(bib, aux, output=child)
    assert second.error
    assert child.read_text() == "\\citation{Used}"
