"""Model semantic decisions are separate from exact local evidence and stub validation."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from test_claims import assert_public_contract

from bib_lint.claims.extractors import codex, model
from bib_lint.claims.protocols import Extractor
from bib_lint.claims.workflow import run_claims


@pytest.fixture
def paper(tmp_path):
    source = tmp_path / "main.tex"
    source.write_text("X is faster\\cite{A} and Y is safer\\cite{B}.\n")
    (tmp_path / "refs.bib").write_text("@article{A,title={One}}\n@article{B,title={Two}}")
    return source


def reply():
    return {
        "items": [
            {
                "citation_id": "citation-0001",
                "disposition": "claims_extracted",
                "claims": [{"file": "main.tex", "claim": "X is faster"}],
                "details": "",
            },
            {
                "citation_id": "citation-0002",
                "disposition": "claims_extracted",
                "claims": [{"file": "main.tex", "claim": "Y is safer"}],
                "details": "",
            },
        ],
        "diagnostics": [],
    }


def test_model_controls_subclaim_boundaries_not_sentence_heuristics(paper, tmp_path, monkeypatch):
    calls = []

    def complete(document, selected_model):
        calls.append((document, selected_model))
        return reply()

    monkeypatch.setattr(codex, "complete", complete)
    result = run_claims(
        paper, bib=[tmp_path / "refs.bib"], model="selected-model", output=tmp_path / "claims"
    )
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert_public_contract(data, "latex")
    assert isinstance(model, Extractor)
    assert calls[0][1] == "selected-model"
    assert len(calls[0][0]["citations"]) == 2
    assert calls[0][0]["sources"][0]["text"] == paper.read_text()
    assert [c["claims"][0]["claim"] for c in data["citations"]] == ["X is faster", "Y is safer"]
    assert data["citations"][1]["claims"][0]["location"]["start"]["column"] == 25
    evidence = yaml.safe_load((tmp_path / "claims/.provenance/provenance.yaml").read_text())
    assert evidence["extraction"]["extractor"]["id"] == "model"
    assert evidence["extraction"]["extractor"]["model"] == "selected-model"
    assert result["extraction"]["state"] == "complete"
    assert all(c["claims"][0]["validation"]["result"] == "valid" for c in data["citations"])


@pytest.mark.parametrize(
    "corruption", ["missing", "duplicate", "invented", "wrong_file", "empty_reason"]
)
def test_bad_model_outputs_fail_without_replacing_artifacts(
    paper, tmp_path, monkeypatch, corruption
):
    value = reply()
    if corruption == "missing":
        value["items"].pop()
    elif corruption == "duplicate":
        value["items"].append(value["items"][0])
    elif corruption == "invented":
        value["items"][0]["claims"][0]["claim"] = "An invented claim."
    elif corruption == "wrong_file":
        value["items"][0]["claims"][0]["file"] = "other.tex"
    else:
        value["items"][0].update(disposition="needs_review", details="")
    monkeypatch.setattr(codex, "complete", lambda *_: value)
    output = tmp_path / "claims"
    output.mkdir()
    existing = output / "claims.yaml"
    existing.write_text("prior complete output")
    with pytest.raises(ValueError):
        run_claims(paper, bib=[tmp_path / "refs.bib"], output=output)
    assert existing.read_text() == "prior complete output"


def test_model_uncertainty_keeps_claims_empty_and_reason_visible(paper, tmp_path, monkeypatch):
    value = reply()
    value["items"][0].update(
        disposition="needs_review", claims=[], details="Citation scope is ambiguous"
    )
    monkeypatch.setattr(codex, "complete", lambda *_: value)
    result = run_claims(paper, bib=[tmp_path / "refs.bib"], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert data["citations"][0]["claims"] == []
    assert result["extraction"]["state"] == "needs_review"
    assert any(
        d["message"] == "Citation scope is ambiguous" for d in result["extraction"]["diagnostics"]
    )
    assert result["summary"]["uncertain_candidates"] == 1
    assert result["summary"]["coverage_diagnostics"] == 0
    summary = Path(result["summary_path"]).read_text()
    assert "uncertain candidates: 1" in summary
    assert "Citation scope is ambiguous (main.tex:1:12)" in summary


def test_repeated_include_model_claims_keep_separate_ids(paper, tmp_path, monkeypatch):
    paper.write_text("\\input{section}\n\\input{section}")
    (tmp_path / "section.tex").write_text("X is faster\\cite{A}.")
    value = reply()
    for item in value["items"]:
        item["claims"] = [{"file": "section.tex", "claim": "X is faster"}]
    monkeypatch.setattr(codex, "complete", lambda *_: value)
    result = run_claims(paper, bib=[tmp_path / "refs.bib"], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert [c["claim_id"] for c in data["citations"][0]["claims"]] == ["claim-0001", "claim-0002"]


def test_codex_transport_uses_schema_stdin_ephemeral_read_only_and_no_tools(monkeypatch):
    seen = {}
    monkeypatch.setattr(codex.shutil, "which", lambda _: "/test/codex")

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        schema = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema.read_text()) == codex.SCHEMA
        answer = Path(command[command.index("--output-last-message") + 1])
        answer.write_text(json.dumps(reply()))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(codex.subprocess, "run", run)
    assert codex.complete({"sources": []}, "selected-model") == reply()
    command = seen["command"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "--ephemeral" in command and "--ignore-user-config" in command
    assert command[command.index("--model") + 1] == "selected-model"
    assert 'web_search="disabled"' in command
    assert "shell_tool" in command and "multi_agent" in command
    assert "DOCUMENT_DATA:" in seen["input"] and "sources" not in " ".join(command)


def test_missing_codex_fails_explicitly_without_local_fallback(paper, tmp_path, monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda _: None)
    with pytest.raises(ValueError, match="requires Codex"):
        run_claims(paper, bib=[tmp_path / "refs.bib"], output=tmp_path / "claims")
    assert not (tmp_path / "claims").exists()
