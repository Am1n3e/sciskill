"""Integrity gates for the real conference-paper build inputs."""

import json
import shutil

import pytest
from pdf_e2e.build import FIXTURES, check_inputs, check_templates


def test_frozen_inputs_cover_every_case_once():
    result = check_inputs(FIXTURES)
    assert result == {"corpora": 3, "entries": 86, "cases": 86}


def test_changed_bibliography_fails_before_building(tmp_path):
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "corpora/representative-20.bib"
    path.write_bytes(path.read_bytes() + b"\n% accidental edit\n")
    with pytest.raises(ValueError, match="checksum.*representative-20.bib"):
        check_inputs(fixtures)


def test_manifest_cannot_silently_drop_a_case(tmp_path):
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "corpora/manifest.json"
    data = json.loads(path.read_text())
    data["corpora"][0]["entry_keys"].pop()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="inventory"):
        check_inputs(fixtures)


def test_all_in_scope_official_templates_are_pinned():
    result = check_templates(FIXTURES)
    assert result == {"venues": 12, "assets": 9, "baseline_builds": 36}


def test_required_venue_cannot_use_an_unresolved_asset(tmp_path):
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "templates.json"
    data = json.loads(path.read_text())
    data["assets"]["icml"]["sha256"] = None
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unpinned.*icml"):
        check_templates(fixtures)
