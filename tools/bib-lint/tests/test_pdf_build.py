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


def _vendored_kit(tmp_path, monkeypatch):
    import hashlib

    from pdf_e2e import assets

    root = tmp_path / "vendored"
    kit = root / "kit"
    kit.mkdir(parents=True)
    (kit / "native.sty").write_bytes(b"% official style\n")
    (kit / "LICENSE").write_bytes(b"Original license notice\n")
    monkeypatch.setattr(assets, "VENDORED_ROOT", root, raising=False)
    pin = {
        "sha256": "0" * 64,
        "files": [
            {"path": "native.sty", "sha256": hashlib.sha256(b"% official style\n").hexdigest()}
        ],
        "notices": [
            {"path": "LICENSE", "sha256": hashlib.sha256(b"Original license notice\n").hexdigest()}
        ],
    }
    return kit, pin


def test_prepare_assets_is_offline_and_copies_only_verified_members_and_notices(
    tmp_path, monkeypatch
):
    import socket

    from pdf_e2e.assets import prepare_asset

    kit, pin = _vendored_kit(tmp_path, monkeypatch)
    (kit / "unselected.tex").write_bytes(b"not a build input")
    monkeypatch.setattr(
        socket, "socket", lambda *args, **kwargs: pytest.fail("Asset network request")
    )
    cache = tmp_path / "cache"
    destination = prepare_asset("kit", pin, cache)
    assert (destination / "native.sty").read_bytes() == b"% official style\n"
    assert (destination / "LICENSE").read_bytes() == b"Original license notice\n"
    assert not (destination / "unselected.tex").exists()
    (destination / "native.sty").write_text("changed cache")
    assert (
        prepare_asset("kit", pin, cache).joinpath("native.sty").read_bytes()
        == b"% official style\n"
    )


@pytest.mark.parametrize("filename", ["native.sty", "LICENSE"])
def test_prepare_assets_rejects_vendored_member_or_notice_drift(tmp_path, monkeypatch, filename):
    from pdf_e2e.assets import prepare_asset

    kit, pin = _vendored_kit(tmp_path, monkeypatch)
    (kit / filename).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        prepare_asset("kit", pin, tmp_path / "cache")


def test_missing_vendored_member_fails_even_with_a_populated_cache(tmp_path, monkeypatch):
    from pdf_e2e.assets import prepare_asset

    kit, pin = _vendored_kit(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    prepare_asset("kit", pin, cache)
    (kit / "native.sty").unlink()
    with pytest.raises(ValueError, match="Missing.*native.sty"):
        prepare_asset("kit", pin, cache)


@pytest.mark.parametrize("member", ["../escaped.sty", "/escaped.sty", "nested\\escaped.sty"])
def test_prepare_assets_rejects_member_path_escape(tmp_path, monkeypatch, member):
    from pdf_e2e.assets import prepare_asset

    _, pin = _vendored_kit(tmp_path, monkeypatch)
    pin["files"][0]["path"] = member
    with pytest.raises(ValueError, match="Unsafe"):
        prepare_asset("kit", pin, tmp_path / "cache")
    assert not (tmp_path / "escaped.sty").exists()


def test_prepare_assets_rejects_symlinked_vendored_members(tmp_path, monkeypatch):
    from pdf_e2e.assets import prepare_asset

    kit, pin = _vendored_kit(tmp_path, monkeypatch)
    target = tmp_path / "outside.sty"
    (kit / "native.sty").rename(target)
    (kit / "native.sty").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        prepare_asset("kit", pin, tmp_path / "cache")


def test_stress_builds_verify_staged_members_and_notices(tmp_path, monkeypatch):
    from pdf_e2e.assets import prepare_asset, verified_asset

    _, pin = _vendored_kit(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    destination = prepare_asset("kit", pin, cache)
    assert verified_asset(pin, cache) == destination
    (destination / "LICENSE").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum.*LICENSE"):
        verified_asset(pin, cache)


def test_asset_archive_identity_cannot_escape_cache(tmp_path, monkeypatch):
    from pdf_e2e.assets import prepare_asset

    _, pin = _vendored_kit(tmp_path, monkeypatch)
    pin["sha256"] = "../escaped"
    with pytest.raises(ValueError, match="archive SHA-256"):
        prepare_asset("kit", pin, tmp_path / "cache")


def test_stress_build_rejects_unverified_extra_cached_files(tmp_path, monkeypatch):
    from pdf_e2e.assets import prepare_asset, verified_asset

    _, pin = _vendored_kit(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    staged = prepare_asset("kit", pin, cache)
    (staged / "shadow.sty").write_bytes(b"not pinned")
    with pytest.raises(ValueError, match="inventory"):
        verified_asset(pin, cache)


def test_required_vendored_assets_match_every_frozen_member_and_notice(tmp_path, monkeypatch):
    import socket

    from pdf_e2e.assets import VENDORED_ROOT, prepare_asset, verified_asset

    monkeypatch.setattr(
        socket, "socket", lambda *args, **kwargs: pytest.fail("Asset network request")
    )
    manifest = json.loads((FIXTURES / "templates.json").read_text())
    assert {p.name for p in VENDORED_ROOT.iterdir() if p.is_dir()} == set(manifest["assets"])
    for asset_id, pin in manifest["assets"].items():
        staged = prepare_asset(asset_id, pin, tmp_path / "cache")
        assert verified_asset(pin, tmp_path / "cache") == staged
        expected = {m["path"] for m in pin["files"] + pin.get("notices", [])}
        assert {str(p.relative_to(staged)) for p in staged.rglob("*") if p.is_file()} == expected
        assert {
            str(p.relative_to(VENDORED_ROOT / asset_id))
            for p in (VENDORED_ROOT / asset_id).rglob("*")
            if p.is_file()
        } == expected
