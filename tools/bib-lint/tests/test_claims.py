"""Reference seeding and exact checks of skill-authored claims; no model client."""

import json
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from bib_lint.claims import load_validator
from bib_lint.claims.protocols import Claim, Extractor, Location, Position, Validation, Validator
from bib_lint.claims.validators import agent, stub
from bib_lint.claims.workflow import run_claims
from bib_lint.cli import main


def assert_public_contract(data, kind):
    assert set(data) == {"schema_version", "scikill_version", "document", "setup", "citations"}
    assert type(data["schema_version"]) is int and data["schema_version"] == 1
    assert isinstance(data["scikill_version"], str) and data["scikill_version"]
    assert set(data["document"]) == {"kind", "path", "sha256"}
    assert data["document"]["kind"] == kind
    assert set(data["setup"]) == {"validation_mode"}
    for citation in data["citations"]:
        assert set(citation) == {"citation_key", "claims"}
        for claim in citation["claims"]:
            assert set(claim) == {"claim_id", "claim", "location", "validation"}
            assert set(claim["validation"]) == {"result", "details"}
            assert claim["validation"]["result"] in {"valid", "invalid", "unresolved"}
            assert claim["validation"]["details"]
            where = claim["location"]
            if kind == "pdf":
                assert set(where) == {"page"}
                assert type(where["page"]) is int and where["page"] >= 1
            else:
                assert set(where) == {"file", "start", "end"}
                for point in (where["start"], where["end"]):
                    assert set(point) == {"line", "column"}


@pytest.fixture
def workspace(tmp_path):
    manuscript = tmp_path / "main.tex"
    manuscript.write_bytes(b"\\input{section}\r\n\\bibliography{refs}\r\n")
    (tmp_path / "section.tex").write_bytes(b"Method X improves accuracy\\cite{A,B}.\r\n")
    (tmp_path / "refs.bib").write_text(
        "@article{A,title={One},author={Jane Smith},year={2024}}\n"
        "@article{B,title={Two}}\n@article{Unused,title={An uncited work}}"
    )
    result = run_claims(manuscript, output=tmp_path / "claims")
    return Path(result["report_path"])


def fill_claim(path, *, result="unresolved", details="Awaiting cited PDF comparison."):
    data = yaml.safe_load(path.read_text())
    claim = {
        "claim_id": "claim-0001",
        "claim": "Method X improves accuracy",
        "location": {
            "file": "section.tex",
            "start": {"line": 1, "column": 1},
            "end": {"line": 1, "column": 27},
        },
        "validation": {"result": result, "details": details},
    }
    for item in data["citations"][:2]:
        item["claims"] = [claim]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return data


def test_seed_reuses_bib_parser_and_does_not_invent_claims(workspace):
    from bib_lint.audit import prepare_input

    data = yaml.safe_load(workspace.read_text())
    assert_public_contract(data, "latex")
    assert data["setup"] == {"validation_mode": "agent"}
    assert [c["citation_key"] for c in data["citations"]] == ["A", "B", "Unused"]
    assert all(c["claims"] == [] for c in data["citations"])
    evidence = yaml.safe_load((workspace.parent / ".provenance/provenance.yaml").read_text())
    parsed, _, _ = prepare_input(workspace.parent.parent / "refs.bib")
    assert set(evidence["references"]) == {i["entry"]["key"] for i in parsed["items"]}
    assert evidence["references"]["A"]["fields"]["title"] == "One"
    assert not (workspace.parent / "sources").exists()


def test_agent_fills_then_program_checks_exact_spans_without_rewriting(workspace):
    fill_claim(workspace, result="invalid", details="The cited PDF reports a lower value (p. 2).")
    before = workspace.read_bytes()
    result = run_claims(workspace)
    assert result["stage"] == "claims_checked" and result["complete"]
    assert result["summary"]["unique_claims"] == 1
    assert result["summary"]["claim_citation_pairs"] == 2
    assert result["summary"]["invalid"] == 2
    assert result["summary"]["valid"] == result["summary"]["unresolved"] == 0
    assert result["summary"]["references_without_claims"] == 1
    assert workspace.read_bytes() == before
    checkpoint = json.loads((workspace.parent / ".provenance/check.json").read_text())
    assert checkpoint["report_sha256"] == sha256(before).hexdigest()
    summary = (workspace.parent / "summary.md").read_text()
    assert "section.tex:1:1" in summary
    assert "claim-0001: invalid" in summary
    assert "Method X improves accuracy" in summary
    assert "The cited PDF reports a lower value (p. 2)." in summary


@pytest.mark.parametrize(
    "change", ["text", "column", "file", "extra", "dropped", "duplicate", "page"]
)
def test_bad_agent_edits_fail_without_clobbering_yaml(workspace, change):
    data = fill_claim(workspace)
    claim = data["citations"][0]["claims"][0]
    if change == "text":
        claim["claim"] = "Invented claim text"
    elif change == "column":
        claim["location"]["end"]["column"] = 25
    elif change == "file":
        claim["location"]["file"] = "refs.bib"
    elif change == "extra":
        data["sources"] = []
    elif change == "dropped":
        data["citations"].pop()
    elif change == "duplicate":
        data["citations"].append(data["citations"][0])
    else:
        claim["location"]["page"] = 1
    workspace.write_text(yaml.safe_dump(data))
    before = workspace.read_bytes()
    with pytest.raises(ValueError):
        run_claims(workspace)
    assert workspace.read_bytes() == before


def test_changed_included_source_is_rejected(workspace):
    fill_claim(workspace)
    (workspace.parent.parent / "section.tex").write_text("Changed manuscript.")
    with pytest.raises(ValueError, match="changed"):
        run_claims(workspace)


def test_duplicate_yaml_keys_are_rejected(workspace):
    with workspace.open("a") as stream:
        stream.write("\nsetup: {validation_mode: agent}\n")
    with pytest.raises(ValueError, match="unique"):
        run_claims(workspace)


def test_no_model_process_is_started_for_latex_seed_or_check(tmp_path, monkeypatch):
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("No nested model or CLI is allowed")

    monkeypatch.setattr(subprocess, "run", forbidden)
    source = tmp_path / "main.tex"
    source.write_text("Method X improves accuracy\\cite{A}.")
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A,title={One}}")
    seeded = run_claims(source, bib=[bib], output=tmp_path / "claims")
    assert seeded["status"] == "awaiting_agent" and not seeded["complete"]
    path = Path(seeded["report_path"])
    data = yaml.safe_load(path.read_text())
    data["citations"][0]["claims"] = [
        {
            "claim_id": "claim-0001",
            "claim": "Method X improves accuracy",
            "location": {
                "file": "main.tex",
                "start": {"line": 1, "column": 1},
                "end": {"line": 1, "column": 27},
            },
            "validation": {"result": "unresolved", "details": "No cited PDF yet."},
        }
    ]
    path.write_text(yaml.safe_dump(data))
    assert run_claims(path)["complete"]


def test_protocols_and_direct_validator_names():
    from bib_lint.claims.extractors import agent as authored
    from bib_lint.claims.extractors import latex, pdf

    for reader in (authored, latex, pdf):
        assert isinstance(reader, Extractor)
    where = Location(Position("main.tex", 1, 1), Position("main.tex", 1, 7))
    claim = Claim("claim-0001", "Claim.", where, Validation("invalid", "Contradicted on p. 2."))
    assert isinstance(stub, Validator) and isinstance(agent, Validator)
    assert load_validator("stub") is stub and load_validator("agent") is agent
    assert stub.validate(claim, "A").to_dict() == {"result": "valid", "details": "Stub mode."}
    assert agent.validate(claim, "A").result == "invalid"
    assert agent.validate(Claim("id", "Claim.", where), "A").result == "unresolved"


@pytest.mark.parametrize("name", ["missing", "../stub", "os.path", "", "_private"])
def test_unknown_validator_names_fail(name):
    with pytest.raises(ValueError, match="validator"):
        load_validator(name)


def test_stub_remains_explicit_testing_mode(workspace):
    data = fill_claim(workspace, result="valid", details="Stub mode.")
    data["setup"]["validation_mode"] = "stub"
    workspace.write_text(yaml.safe_dump(data))
    assert run_claims(workspace)["setup"] == {"validation_mode": "stub"}
    with pytest.raises(ValueError, match="match"):
        run_claims(workspace, mode="agent")
    data["citations"][0]["claims"][0]["validation"]["result"] = "invalid"
    workspace.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="validator mode"):
        run_claims(workspace)


def test_cli_seed_then_check_and_removed_model_option(tmp_path, capsys):
    source = tmp_path / "main.tex"
    source.write_text("A manuscript.")
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A,title={One}}")
    args = [
        "check-claims",
        str(source),
        "--bib",
        str(bib),
        "--output",
        str(tmp_path / "claims"),
        "--json",
    ]
    assert main(args) == 0
    seeded = json.loads(capsys.readouterr().out)
    assert seeded["status"] == "awaiting_agent" and not seeded["complete"]
    assert main(["check-claims", seeded["report_path"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "claims_checked"
    assert main([*args, "--model", "anything"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_installed_producer_version_is_recorded(workspace, monkeypatch):
    from importlib.metadata import PackageNotFoundError

    from bib_lint.claims import report

    monkeypatch.setattr(report, "version", lambda name: "9.8.7+test")
    assert (
        report.header({"kind": "pdf", "path": "a.pdf", "sha256": "a" * 64}, "agent")[
            "scikill_version"
        ]
        == "9.8.7+test"
    )

    def standalone(name):
        if name == "sciskill":
            raise PackageNotFoundError(name)
        assert name == "bib-lint"
        return "2.3.4"

    monkeypatch.setattr(report, "version", standalone)
    assert report.producer_version() == "2.3.4"
