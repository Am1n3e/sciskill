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


def test_prepare_assets_copies_only_verified_members(tmp_path):
    import hashlib
    import zipfile

    from pdf_e2e.assets import prepare_asset

    archive = tmp_path / "kit.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("kit/native.sty", b"% official style\n")
        zipped.writestr("kit/unselected.tex", b"not a build input")
    pin = {
        "url": "https://conference.example/kit.zip",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "bytes": archive.stat().st_size,
        "root": "kit/",
        "files": [
            {"path": "native.sty", "sha256": hashlib.sha256(b"% official style\n").hexdigest()}
        ],
    }
    destination = prepare_asset("kit", pin, tmp_path)
    assert (destination / "native.sty").read_bytes() == b"% official style\n"
    assert not (destination / "unselected.tex").exists()
    (destination / "native.sty").write_text("changed")
    assert (
        prepare_asset("kit", pin, tmp_path).joinpath("native.sty").read_bytes()
        == b"% official style\n"
    )


def test_prepare_assets_rejects_archive_drift(tmp_path):
    from pdf_e2e.assets import prepare_asset

    (tmp_path / "kit.zip").write_bytes(b"altered archive")
    with pytest.raises(ValueError, match="checksum"):
        prepare_asset("kit", {"sha256": "0" * 64}, tmp_path)


def test_prepare_assets_rejects_member_path_escape(tmp_path):
    import hashlib
    import zipfile

    from pdf_e2e.assets import prepare_asset

    archive = tmp_path / "kit.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../escaped.sty", b"no")
    pin = {
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "bytes": archive.stat().st_size,
        "root": "",
        "files": [{"path": "../escaped.sty", "sha256": hashlib.sha256(b"no").hexdigest()}],
    }
    with pytest.raises(ValueError, match="Unsafe"):
        prepare_asset("kit", pin, tmp_path)
    assert not (tmp_path / "escaped.sty").exists()


def test_stress_builds_verify_staged_template_members(tmp_path):
    import hashlib

    from pdf_e2e.assets import verified_asset

    pin = {
        "sha256": "0" * 64,
        "files": [{"path": "native.sty", "sha256": hashlib.sha256(b"official").hexdigest()}],
    }
    member = tmp_path / pin["sha256"] / "native.sty"
    member.parent.mkdir()
    member.write_bytes(b"official")
    assert verified_asset(pin, tmp_path) == member.parent
    member.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum.*native.sty"):
        verified_asset(pin, tmp_path)
