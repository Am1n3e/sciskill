import copy
import json
from pathlib import Path

import pytest
from provider_support import fixture_registry
from support import FakeClient

from bib_lint.audit import Workspace, audit_summary, run_audit
from bib_lint.scope import fingerprint, validate_report
from bib_lint.storage import report_lock, write_json
from bib_lint.verification.matching import select_result
from bib_lint.viewer.data import load_report

BIB = "@book{A,title={One},author={Jane Smith},year={2025}}\n@book{B,title={Two}}"


@pytest.fixture
def bib(tmp_path):
    path = tmp_path / "refs.bib"
    path.write_text(BIB)
    return path


def found(record, client):
    return select_result("test", record, [copy.deepcopy(record)], authority=True)


def audit(bib, **kwargs):
    return run_audit(bib, client=FakeClient(), methods=fixture_registry({"test": found}), **kwargs)


def test_all_scope_partial_and_resume(bib):
    original = bib.read_bytes()
    workspace, report, _ = audit(bib, citation_key="a")
    assert workspace.root == bib.with_name("refs.bib-lint")
    assert report["schema_version"] == 3
    assert report["verification_scope"] == {"mode": "all", "eligible_keys": ["A", "B"]}
    assert all("is_used" not in i["validations"] for i in report["items"])
    counts = audit_summary(report)
    assert (counts["completed"], counts["pending"], counts["used"], counts["unused"]) == (
        1,
        1,
        None,
        None,
    )
    assert workspace.checkpoint.exists() and not workspace.final.exists()
    prior = copy.deepcopy(report["items"][0]["validations"])
    _, report, _ = audit(bib, citation_key="B", refresh=True)
    assert workspace.final.exists() and not workspace.checkpoint.exists()
    assert report["items"][0]["validations"] == prior
    assert bib.read_bytes() == original


def test_aux_recursive_warnings_preview_and_no_eligible(bib, tmp_path):
    aux = tmp_path / "root.aux"
    child = tmp_path / "child.aux"
    aux.write_text(r"\@input{child.aux}")
    child.write_text(r"\citation{a,missing}")
    originals = aux.read_bytes(), child.read_bytes()
    workspace, report, warnings = audit(bib, aux=aux, preview=True)
    assert report["verification_scope"]["eligible_keys"] == ["A"]
    assert warnings == ["Missing citation keys: missing"]
    assert "verification_run" not in report
    assert not workspace.cache.exists()
    _, report, _ = audit(bib, aux=aux)
    assert report["verification_run"]["complete"]
    assert audit_summary(report)["unused"] == 1
    assert (aux.read_bytes(), child.read_bytes()) == originals
    child.write_text(r"\relax")
    _, report, _ = run_audit(
        bib,
        aux=aux,
        output=tmp_path / "empty",
        client=FakeClient(),
        methods=fixture_registry({"test": lambda *_: pytest.fail("No eligible entries")}),
    )
    assert audit_summary(report)["eligible"] == 0


def test_empty_bibliography_and_paths(tmp_path, monkeypatch):
    bib = tmp_path / "empty.bib"
    bib.write_text("% empty")
    monkeypatch.chdir(tmp_path)
    workspace, report, _ = audit(bib, output="nested/audit")
    assert workspace.root == tmp_path / "nested/audit"
    assert report["verification_run"]["complete"]
    assert workspace.cache.is_dir()
    assert Workspace.for_input(tmp_path / "legacy.tmp.json").root == tmp_path / "legacy.bib-lint"
    with pytest.raises(ValueError, match="directory"):
        audit(bib, output=bib)


def test_bad_input_or_key_creates_no_output(bib, tmp_path):
    for key in ["missing"]:
        with pytest.raises(ValueError, match="Citation key"):
            audit(bib, citation_key=key)
    assert not Workspace.for_input(bib).root.exists()
    bib.write_text("@book{x,title=undefined}")
    with pytest.raises(ValueError):
        audit(bib)
    assert not Workspace.for_input(bib).root.exists()


def test_stale_input_refresh_and_parse_preserve_saved(bib):
    workspace, _, _ = audit(bib)
    previous = workspace.final.read_bytes()
    bib.write_text(BIB.replace("One", "Changed"))
    for options in [{"refresh": True}, {"preview": True}]:
        with pytest.raises(ValueError, match="new output directory"):
            audit(bib, **options)
        assert workspace.final.read_bytes() == previous
        assert not workspace.checkpoint.exists()


@pytest.mark.parametrize("target", ["report.json", "report.tmp.json"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_input_alias_protection(bib, target, alias):
    workspace = Workspace.for_input(bib)
    workspace.root.mkdir()
    path = workspace.root / target
    getattr(path, "symlink_to" if alias == "symlink" else "hardlink_to")(bib)
    with pytest.raises(ValueError, match="must not overwrite"):
        audit(bib)
    assert bib.read_text() == BIB


def test_included_aux_alias_and_external_lock(bib, tmp_path):
    aux = tmp_path / "root.aux"
    child = tmp_path / "child.aux"
    aux.write_text(r"\@input{child.aux}")
    child.write_text(r"\citation{A}")
    workspace = Workspace.for_input(bib)
    workspace.root.mkdir()
    workspace.checkpoint.hardlink_to(child)
    with pytest.raises(ValueError, match="must not overwrite"):
        audit(bib, aux=aux)
    workspace.checkpoint.unlink()
    with report_lock(workspace.final), pytest.raises(ValueError, match="already in use"):
        audit(bib)
    assert child.read_text() == r"\citation{A}"


def test_interrupt_refresh_and_policy_registry_recompute(bib, monkeypatch):
    workspace, report, _ = audit(bib)
    previous = workspace.final.read_bytes()

    def interrupted(*_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_audit(
            bib,
            refresh=True,
            client=FakeClient(),
            methods=fixture_registry({"test": found, "second": interrupted}),
        )
    assert workspace.final.read_bytes() == previous
    checkpoint = load_report(workspace.root)
    assert not checkpoint["verification_run"]["complete"]
    assert checkpoint["items"][0]["validations"]["correctness"]["methods"][0]["name"] == "test"
    # Same registry, changed policy recomputes instead of resuming the old outcome.
    checkpoint["verification_run"]["policy_version"] = 3
    write_json(workspace.checkpoint, checkpoint)
    calls = []

    def again(record, client):
        calls.append(record["title"])
        return found(record, client)

    run_audit(bib, client=FakeClient(), methods=fixture_registry({"test": again, "second": again}))
    assert len(calls) == 4


@pytest.mark.parametrize("fault", ["write", "promote"])
def test_fault_preserves_prior_final(bib, monkeypatch, fault):
    workspace, _, _ = audit(bib)
    previous = workspace.final.read_bytes()
    if fault == "write":

        def fail(*_):
            raise OSError("disk full")

        monkeypatch.setattr("bib_lint.verification._write_json", fail)
    else:
        original = Path.replace

        def replace(path, target):
            if path == workspace.checkpoint and target == workspace.final:
                raise OSError("rename failed")
            return original(path, target)

        monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError):
        audit(bib, refresh=True)
    assert workspace.final.read_bytes() == previous
    if fault == "promote":
        assert workspace.checkpoint.exists()


def test_import_legacy_reuses_compatible_and_preserves_inputs(bib, tmp_path):
    from bib_lint.verification import verify_file
    from bib_lint.workflow import parse_bib

    aux = tmp_path / "paper.aux"
    aux.write_text(r"\citation{A}")
    parsed, _ = parse_bib(bib, aux)
    legacy, _ = verify_file(
        parsed.output, client=FakeClient(), methods=fixture_registry({"test": found})
    )
    before = legacy.read_bytes()
    sidecar = legacy.with_suffix(".agent.json")
    sidecar.write_text("manual evidence")
    workspace, report, _ = run_audit(
        legacy,
        output=tmp_path / "import",
        client=FakeClient(),
        methods=fixture_registry({"test": lambda *_: pytest.fail("Compatible outcome rerun")}),
    )
    assert report["verification_run"]["fingerprint"] == fingerprint(report)
    assert legacy.read_bytes() == before and sidecar.read_text() == "manual evidence"
    assert workspace.final.exists()
    data = json.loads(before)
    data["items"][0]["validations"].pop("is_used")
    legacy.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="bibliography directly"):
        audit(legacy, output=tmp_path / "unknown")
    assert not (tmp_path / "unknown").exists()


def test_checkpoint_precedence_and_malformed_error(bib):
    workspace, report, _ = audit(bib)
    report["verification_run"]["complete"] = False
    write_json(workspace.checkpoint, report)
    assert not load_report(workspace.root)["verification_run"]["complete"]
    workspace.checkpoint.write_text("{broken")
    with pytest.raises(ValueError):
        load_report(workspace.root)
    workspace.checkpoint.unlink()
    assert load_report(workspace.root)["verification_run"]["complete"]


def test_atomic_writer_cleans_up_failed_replace(tmp_path, monkeypatch):
    final = tmp_path / "report.json"
    final.write_text("old")

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        write_json(final, {"new": True})
    assert final.read_text() == "old"
    assert list(tmp_path.iterdir()) == [final]


@pytest.mark.parametrize("scope", [None, {"mode": "all", "eligible_keys": []}, {"mode": "unknown"}])
def test_invalid_schema3_scope_rejected(scope):
    report = {
        "schema_version": 3,
        "items": [{"entry": {"key": "x", "fields": {}, "persons": {}}, "validations": {}}],
        "verification_scope": scope,
    }
    with pytest.raises(ValueError):
        validate_report(report)


def test_comment_only_changes_and_preview_preserve_existing_decisions(bib):
    workspace, report, _ = audit(bib)
    previous = workspace.final.read_bytes()
    bib.write_text("% comment changed\n" + BIB)
    audit(bib, preview=True)
    assert workspace.final.read_bytes() == previous and not workspace.checkpoint.exists()
    run_audit(
        bib,
        client=FakeClient(),
        methods=fixture_registry({"test": lambda *_: pytest.fail("Comment reran provider")}),
    )


def test_json_ambiguous_key_and_unknown_usage_no_artifacts(tmp_path):
    from support import ENTRY

    source = tmp_path / "input.json"
    data = {
        "schema_version": 2,
        "items": [
            {"entry": {**ENTRY, "key": key}, "validations": {"is_used": True}} for key in ["A", "a"]
        ],
    }
    source.write_text(json.dumps(data))
    before = source.read_bytes()
    with pytest.raises(ValueError, match="exactly one"):
        audit(source, citation_key="a")
    assert source.read_bytes() == before and not Workspace.for_input(source).root.exists()


@pytest.mark.parametrize("mutation", ["field", "person", "scope", "run", "summary", "correctness"])
def test_malformed_report_rejected_before_workspace(tmp_path, mutation):
    from support import ENTRY

    source = tmp_path / "bad.json"
    report = {
        "schema_version": 3,
        "items": [{"entry": copy.deepcopy(ENTRY), "validations": {}}],
        "verification_scope": {"mode": "all", "eligible_keys": ["Example"]},
    }
    if mutation == "field":
        report["items"][0]["entry"]["fields"]["title"] = None
    elif mutation == "person":
        report["items"][0]["entry"]["persons"]["author"][0]["first"] = "Jane"
    elif mutation == "scope":
        report["verification_scope"]["mode"] = []
    elif mutation == "run":
        report["verification_run"] = [1]
    elif mutation == "summary":
        report["summary"] = []
    else:
        report["items"][0]["validations"]["correctness"] = {"methods": [None]}
    source.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        audit(source)
    assert not Workspace.for_input(source).root.exists()


def test_schema3_malformed_checkpoint_never_falls_back(bib):
    workspace, report, _ = audit(bib)
    report["verification_scope"]["eligible_keys"] = []
    write_json(workspace.checkpoint, report)
    with pytest.raises(ValueError, match="scope"):
        load_report(workspace.root)


@pytest.mark.parametrize(
    "outcome",
    [
        {"name": "test", "status": "found", "found_ref": []},
        {"name": "test", "status": "found", "found_ref": {"authors": [None]}},
        {"name": "test", "status": "error", "comparisons": [None]},
    ],
)
def test_malformed_saved_outcome_rejected_without_replacement(bib, outcome):
    workspace, report, _ = audit(bib)
    previous = workspace.final.read_bytes()
    report["items"][0]["validations"]["correctness"]["methods"] = [outcome]
    write_json(workspace.checkpoint, report)
    saved = workspace.checkpoint.read_bytes()
    with pytest.raises(ValueError, match="source|Source"):
        audit(bib)
    assert workspace.final.read_bytes() == previous and workspace.checkpoint.read_bytes() == saved
