"""Generated projects preserve citations and use native conference formatting."""

import dataclasses
import re

import pytest
from pdf_e2e.build import FIXTURES, read_json

from bib_lint.parser import parse_file, parse_string


@pytest.mark.parametrize("corpus", ["representative-20", "rule-variants", "adversarial"])
def test_build_keys_change_no_citation_metadata(corpus):
    from pdf_e2e.projects import build_bibliography

    source = FIXTURES / "corpora" / f"{corpus}.bib"
    before = source.read_bytes()
    text, key_map = build_bibliography(source)
    original = parse_file(source).entries
    derived = parse_string(text).entries
    assert len(key_map) == len(original) == len(derived)
    assert set(derived) == set(key_map.values())
    assert all(re.fullmatch(r"ref[0-9]{4}", key) for key in derived)
    for old, new in key_map.items():
        assert dataclasses.replace(original[old], key=new) == derived[new]
    assert source.read_bytes() == before


@pytest.mark.parametrize("venue", read_json(FIXTURES / "templates.json")["venues"])
def test_native_project_cites_every_reference_without_answer_markers(venue):
    from pdf_e2e.projects import paper_source

    keys = ["ref0001", "ref0002", "ref0003"]
    text = paper_source(venue, keys)
    assert all(key in text for key in keys)
    assert r"\cite{" in text
    assert r"\bibliography{references}" in text
    assert venue["style_package"]["name"] in text
    assert (r"\bibliographystyle{" in text) != venue["bibliography"]["selected_by_style"]
    assert not any(
        marker in text.lower() for marker in ("case_", "adversarial", "expected", "corrupt")
    )
    if venue["id"] == "aaai":
        assert "hyperref" not in text
    if venue["family"] == "cvpr":
        assert r"\def\confName{" + venue["id"].upper() + "}" in text


def test_project_cache_changes_with_body_and_tracks_all_inputs(tmp_path, monkeypatch):
    import hashlib
    import json

    from pdf_e2e import projects

    venue = read_json(FIXTURES / "templates.json")["venues"][0]
    corpus = read_json(FIXTURES / "corpora/manifest.json")["corpora"][0]
    asset = tmp_path / "asset"
    asset.mkdir()
    (asset / "native.sty").write_text("% preserve style notice\n")
    first = projects.create_project(venue, corpus, asset, FIXTURES, tmp_path / "projects")
    recipe = read_json(first / "recipe.json")
    assert len(recipe["key_map"]) == 20
    assert recipe["files"]["native.sty"] == hashlib.sha256(b"% preserve style notice\n").hexdigest()
    assert set(recipe["files"]) >= {"main.tex", "references.bib", "native.sty"}
    assert recipe["corpus"]["sha256"] == corpus["sha256"]
    body = tmp_path / "body.tex"
    body.write_text(projects.BODY.read_text() + "\nAdditional discussion.\n")
    monkeypatch.setattr(projects, "BODY", body)
    second = projects.create_project(venue, corpus, asset, FIXTURES, tmp_path / "projects")
    assert second != first
    assert first.joinpath("main.tex").read_bytes() != second.joinpath("main.tex").read_bytes()
    assert json.loads(first.joinpath("recipe.json").read_text()) == recipe


def test_icml_has_the_required_corresponding_author():
    from pdf_e2e.projects import paper_source

    venue = next(v for v in read_json(FIXTURES / "templates.json")["venues"] if v["id"] == "icml")
    assert r"\icmlcorrespondingauthor{Anonymous Author}{anonymous@example.org}" in paper_source(
        venue, ["ref0001"]
    )


@pytest.mark.parametrize("name", ["cvpr", "iccv"])
def test_vision_bibliography_uses_native_small_font(name):
    from pdf_e2e.projects import paper_source

    venue = next(v for v in read_json(FIXTURES / "templates.json")["venues"] if v["id"] == name)
    source = paper_source(venue, ["ref0001"])
    assert "{\\small\n\\bibliographystyle{ieeenat_fullname}" in source
    assert "\\bibliography{references}\n}" in source


def test_explicit_subset_preserves_selected_metadata_and_records_exclusions(tmp_path):
    import dataclasses

    from pdf_e2e.projects import build_bibliography

    source = FIXTURES / "corpora/adversarial.bib"
    selected = ["adv_match_title_tex_emphasis", "adv_provider_shadowed_version_pin"]
    text, key_map = build_bibliography(source, selected_keys=selected)
    original = parse_file(source).entries
    rendered = parse_string(text).entries
    assert list(key_map) == selected
    assert len(rendered) == 2
    for old, new in key_map.items():
        assert dataclasses.replace(original[old], key=new) == rendered[new]


def test_subset_rejects_unknown_or_duplicate_source_keys():
    from pdf_e2e.projects import build_bibliography

    source = FIXTURES / "corpora/adversarial.bib"
    with pytest.raises(ValueError, match="selection"):
        build_bibliography(source, selected_keys=["missing"])
    with pytest.raises(ValueError, match="selection"):
        build_bibliography(source, selected_keys=["adv_match_title_tex_emphasis"] * 2)
