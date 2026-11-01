"""PR audits select committed, genuinely new citation identities before any lookup."""

import json
import subprocess

import pytest
from provider_support import fixture_registry
from support import FakeClient

from bib_lint.audit import audit_summary, prepare_input, run_audit
from bib_lint.cli import main
from bib_lint.verification.matching import select_result

OLD = "@book{Old,title={Original},author={Jane Smith},year={2025}}\n"
NEW = "@book{New,title={New work},author={Jane Smith},year={2026}}\n"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root):
    git(root, "add", "--all")
    git(root, "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-qb", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "refs.bib").write_text(OLD)
    commit(root)
    return root


def audit(source, **kwargs):
    return run_audit(source, client=FakeClient(), **kwargs)


def test_only_new_entries_are_queried_and_worktree_is_ignored(repo, tmp_path):
    base = git(repo, "rev-parse", "HEAD")
    source = repo / "refs.bib"
    source.write_text(OLD.replace("Original", "Edited") + NEW)
    head = commit(repo)
    source.write_text("uncommitted invalid BibTeX")
    seen = []

    def found(record, client):
        seen.append(record["title"])
        return select_result("test", record, [record], authority=True)

    _, report, _ = audit(
        source,
        base=base,
        head=head,
        output=tmp_path / "audit",
        methods=fixture_registry({"test": found}),
    )
    assert seen == ["New work"]
    assert [i["entry"]["key"] for i in report["items"]] == ["New"]
    assert report["selection"]["merge_base"] == base
    assert report["selection"]["head"] == head
    assert report["selection"]["keys"] == ["New"]
    assert audit_summary(report)["completed"] == 1
    assert audit_summary(report)["used"] is None
    assert source.read_text() == "uncommitted invalid BibTeX"


def test_merge_base_not_target_tip_and_keys_moved_between_files(repo):
    git(repo, "switch", "-qc", "paper")
    (repo / "refs.bib").write_text(NEW)
    head = commit(repo)
    git(repo, "switch", "-q", "main")
    (repo / "refs.bib").write_text(OLD + NEW)
    commit(repo)
    report, _, _ = prepare_input(repo / "refs.bib", base="main", head=head)
    assert [i["entry"]["key"] for i in report["items"]] == ["New"]
    git(repo, "switch", "-q", "paper")
    (repo / "refs.bib").unlink()
    (repo / "renamed.bib").write_text(OLD.replace("Old", "old") + NEW)
    commit(repo)
    report, _, _ = prepare_input(repo / "renamed.bib", base="main")
    assert [i["entry"]["key"] for i in report["items"]] == ["New"]


def test_no_new_keys_completes_without_lookups(repo, tmp_path):
    source = repo / "refs.bib"
    base = git(repo, "rev-parse", "HEAD")
    source.write_text(OLD.replace("Original", "Reformatted"))
    commit(repo)
    _, report, _ = audit(
        source,
        base=base,
        output=tmp_path / "none",
        methods=fixture_registry({"test": lambda *_: pytest.fail("No lookup expected")}),
    )
    assert report["verification_run"]["complete"]
    assert audit_summary(report)["eligible"] == 0
    assert report["selection"]["keys"] == []


def test_new_file_preserves_string_expansion_and_existing_keys(repo):
    (repo / "new.bib").write_text(
        '@string{label="New work"}\n' + NEW.replace("{New work}", "label") + OLD
    )
    commit(repo)
    report, _, _ = prepare_input(repo / "new.bib", base="HEAD~1")
    assert len(report["items"]) == 1
    assert report["items"][0]["entry"]["fields"]["title"] == "New work"


@pytest.mark.parametrize("options", [{"aux": "paper.aux", "base": "HEAD"}, {"head": "HEAD~1"}])
def test_incompatible_scope_options_fail_before_writes(repo, options):
    with pytest.raises(ValueError):
        prepare_input(repo / "refs.bib", **options)
    assert not (repo / "refs.bib-lint").exists()


def test_bad_revisions_missing_file_and_symlinks_fail_closed(repo):
    source = repo / "refs.bib"
    for base in ["missing-ref", "--help"]:
        with pytest.raises(ValueError):
            prepare_input(source, base=base)
    with pytest.raises(ValueError):
        prepare_input(repo / "missing.bib", base="HEAD")
    source.unlink()
    source.symlink_to("outside.bib")
    commit(repo)
    with pytest.raises(ValueError, match="regular file"):
        prepare_input(source, base="HEAD~1")


def test_broken_baseline_is_not_treated_as_empty(repo):
    source = repo / "refs.bib"
    source.write_text("@book{bad,title=undefined}")
    commit(repo)
    source.write_text(NEW)
    commit(repo)
    with pytest.raises(ValueError):
        prepare_input(source, base="HEAD~1")


def test_cli_git_selection_and_invalid_exit_are_explicit(repo, tmp_path, monkeypatch, capsys):
    source = repo / "refs.bib"
    source.write_text(OLD + NEW)
    commit(repo)

    def mismatch(record, client):
        other = {**record, "year": 2020}
        return select_result("test", record, [other], authority=True)

    def run(*args, **kwargs):
        return audit(*args, **kwargs, methods=fixture_registry({"test": mismatch}))

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    args = ["verify", str(source), "--base", "HEAD~1", "--json", "--output", str(tmp_path / "cli")]
    assert main(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["selection"]["keys"] == ["New"]
    assert value["summary"]["invalid"] == 1
    assert main([*args, "--fail-on-invalid"]) == 1
    assert json.loads(capsys.readouterr().out)["complete"]


def test_unresolved_does_not_fail_the_invalid_gate(repo, tmp_path, monkeypatch, capsys):
    (repo / "refs.bib").write_text(OLD + NEW)
    commit(repo)

    def run(*args, **kwargs):
        return audit(
            *args, **kwargs, methods=fixture_registry({"test": lambda *_: {"candidates": []}})
        )

    monkeypatch.setattr("bib_lint.cli.run_audit", run)
    assert (
        main(
            [
                "verify",
                str(repo / "refs.bib"),
                "--base",
                "HEAD~1",
                "--json",
                "--output",
                str(tmp_path / "unknown"),
                "--fail-on-invalid",
            ]
        )
        == 0
    )
    value = json.loads(capsys.readouterr().out)
    assert value["summary"]["unresolved"] == 1


def test_resume_is_bound_to_the_same_git_comparison(repo, tmp_path):
    (repo / "refs.bib").write_text(OLD + NEW)
    commit(repo)
    source = repo / "refs.bib"
    workspace, report, _ = audit(source, base="HEAD~1", output=tmp_path / "bound", preview=True)
    assert report["audit_input"]["head"] == git(repo, "rev-parse", "HEAD")
    (repo / "note.txt").write_text("new revision, same bibliography")
    commit(repo)
    with pytest.raises(ValueError, match="different inputs"):
        audit(source, base="HEAD~2", output=workspace.root, preview=True)


def test_selection_cannot_claim_keys_absent_from_the_report(repo):
    from bib_lint.scope import validate_report

    report, _, _ = prepare_input(repo / "refs.bib", base="HEAD")
    report["selection"]["keys"] = ["not-in-report"]
    with pytest.raises(ValueError, match="selection"):
        validate_report(report)
