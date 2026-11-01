"""Claim extraction/validation contracts, independent of scholarly providers."""

import json
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from bib_lint.claims import load_validator
from bib_lint.claims.protocols import (
    Claim,
    Extraction,
    Extractor,
    Location,
    Position,
    Source,
    Validation,
    Validator,
)
from bib_lint.claims.validators import stub
from bib_lint.claims.workflow import build_report, run_claims
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


def test_stub_is_the_validator_module_and_satisfies_protocol():
    claim = Claim(
        "claim-0001",
        "A numerical claim is 56.7%.",
        Location(Position("main.tex", 1, 1), Position("main.tex", 1, 27)),
    )
    assert isinstance(stub, Validator)
    assert load_validator("stub") is stub
    assert stub.validate(claim, "smith2024").to_dict() == {
        "result": "valid",
        "details": "Stub mode.",
    }


@pytest.mark.parametrize("name", ["missing", "../stub", "os.path", "", "_private"])
def test_unknown_or_unsafe_validator_names_fail(name):
    with pytest.raises(ValueError, match="validator"):
        load_validator(name)


def test_latex_cli_grouping_exact_spans_and_stub(tmp_path, capsys, monkeypatch):
    from bib_lint.claims.extractors import codex

    def complete(document, model):
        quotes = [
            ("paper with spaces.tex", r"Method X improves accuracy by 5\%\citep{A,B}."),
            ("section.tex", r"It is faster\citep{A}."),
        ]
        return {
            "items": [
                {
                    "citation_id": c["citation_id"],
                    "disposition": "claims_extracted",
                    "claims": [{"file": file, "claim": quote}],
                    "details": "",
                }
                for c, (file, quote) in zip(document["citations"], quotes, strict=True)
            ],
            "diagnostics": [],
        }

    monkeypatch.setattr(codex, "complete", complete)
    source = tmp_path / "paper with spaces.tex"
    source.write_bytes(
        b"\\begin{document}\r\n"
        b"Method X improves accuracy by 5\\%\\citep{A,B}.\r\n"
        b"\\input{section}\r\n"
        b"\\end{document}\r\n"
    )
    child = tmp_path / "section.tex"
    child.write_text("It is faster\\citep{A}.\n% Hidden claim\\cite{B}.\n")
    bib = tmp_path / "references.bib"
    bib.write_text("@article{A,title={One}}\n@article{B,title={Two}}")
    before = {p: p.read_bytes() for p in (source, child, bib)}
    output = tmp_path / "claims"
    assert (
        main(
            [
                "check-claims",
                str(source),
                "--bib",
                str(bib),
                "--mode",
                "stub",
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "check-claims"
    assert result["complete"] is True
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert_public_contract(data, "latex")
    assert data["setup"]["validation_mode"] == "stub"
    citations = {item["citation_key"]: item["claims"] for item in data["citations"]}
    assert set(citations) == {"A", "B"}
    assert len(citations["A"]) == 2 and len(citations["B"]) == 1
    assert citations["A"][0]["claim_id"] == citations["B"][0]["claim_id"]
    assert citations["A"][0]["claim"] == "Method X improves accuracy by 5\\%\\citep{A,B}."
    assert citations["A"][1]["claim"] == "It is faster\\citep{A}."
    for claims in citations.values():
        for claim in claims:
            assert set(claim) == {"claim_id", "claim", "location", "validation"}
            assert claim["validation"] == {"result": "valid", "details": "Stub mode."}
            location = claim["location"]
            start, end = location["start"], location["end"]
            text = before[tmp_path / location["file"]].decode()
            lines = text.splitlines(keepends=True)
            a = sum(map(len, lines[: start["line"] - 1])) + start["column"] - 1
            b = sum(map(len, lines[: end["line"] - 1])) + end["column"] - 1
            assert text[a:b] == claim["claim"]
    assert result["summary"]["unique_claims"] == 2
    assert result["summary"]["claim_citation_pairs"] == 3
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_invalid_mode_does_not_create_or_replace_output(tmp_path, capsys):
    output = tmp_path / "saved"
    output.mkdir()
    report = output / "claims.yaml"
    report.write_text("previous output")
    assert (
        main(
            [
                "check-claims",
                str(tmp_path / "missing.tex"),
                "--mode",
                "os.path",
                "--output",
                str(output),
                "--json",
            ]
        )
        == 2
    )
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "check-claims"
    assert result["status"] == "failed"
    assert "validator" in result["error"]["message"].lower()
    assert report.read_text() == "previous output"


def test_reference_command_renamed(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    help_text = capsys.readouterr().out
    assert "check-references" in help_text and "check-claims" in help_text
    assert main(["verify", "missing.bib", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_extractor_module_protocol():
    from bib_lint.claims.extractors import latex, pdf

    assert isinstance(latex, Extractor)
    assert isinstance(pdf, Extractor)


def run_local(path, **kwargs):
    """Exercise the deterministic source readers without a model request."""
    from bib_lint.claims.extractors import latex, pdf

    reader = pdf if Path(path).suffix.lower() == ".pdf" else latex
    return run_claims(path, extractor=reader, **kwargs)


def make_project(tmp_path, text):
    source = tmp_path / "main.tex"
    source.write_text(text)
    bib = tmp_path / "references.bib"
    bib.write_text("@article{A,title={One},author={Jane Smith},year={2024}}")
    return source, bib


def test_grouped_and_repeated_occurrences_have_distinct_identity(tmp_path):
    source, bib = make_project(tmp_path, "\\input{section}\n\\input{section}")
    (tmp_path / "section.tex").write_text("Method works\\cite{A}.")
    result = run_local(source, bib=[bib], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    claims = data["citations"][0]["claims"]
    assert [c["claim_id"] for c in claims] == ["claim-0001", "claim-0002"]
    assert claims[0]["claim"] == claims[1]["claim"]
    assert claims[0]["location"] == claims[1]["location"]


def test_comments_macro_definitions_and_literal_code_are_not_citations(tmp_path):
    source, bib = make_project(
        tmp_path,
        r"""
\newcommand{\fake}{Hidden claim\cite{A}.}
% Hidden claim\cite{A}.
\begin{verbatim}
Hidden claim\cite{A}.
\end{verbatim}
\verb|Hidden claim\cite{A}.|
\nocite{A}
\section{Results}
Method improves by 56.7\%\citep[see][p.~2]{A}.
""",
    )
    result = run_local(source, bib=[bib], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert result["summary"]["citation_occurrences"] == 1
    assert data["citations"][0]["claims"][0]["claim"] == (
        r"Method improves by 56.7\%\citep[see][p.~2]{A}."
    )


def test_missing_key_and_bare_citation_preserved_as_diagnostics(tmp_path):
    source, bib = make_project(tmp_path, "A method works\\cite{unknown}.\n\n\\cite{A}\n")
    result = run_local(source, bib=[bib], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert data["citations"] == [{"citation_key": "A", "claims": []}]
    codes = {d["code"] for d in result["extraction"]["diagnostics"]}
    assert codes >= {"unresolved_citation", "no_claim"}
    assert result["summary"]["claim_citation_pairs"] == 0


@pytest.mark.parametrize("include", ["../outside", "main"])
def test_include_escape_and_cycles_fail_before_output(tmp_path, include):
    source, bib = make_project(tmp_path, f"\\input{{{include}}}")
    with pytest.raises(ValueError):
        run_local(source, bib=[bib], output=tmp_path / "claims")
    assert not (tmp_path / "claims").exists()


def test_identical_rerun_reuses_output_changed_input_preserves_previous(tmp_path):
    source, bib = make_project(tmp_path, "Method works\\cite{A}.")
    output = tmp_path / "claims"
    first = run_local(source, bib=[bib], output=output)
    contents = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert run_local(source, bib=[bib], output=output) == first
    source.write_text("A different method works\\cite{A}.")
    with pytest.raises(ValueError, match="different content"):
        run_local(source, bib=[bib], output=output)
    assert all(p.read_bytes() == raw for p, raw in contents.items())


def test_stub_does_not_bypass_source_fidelity_and_validator_is_replaceable(tmp_path):
    from types import SimpleNamespace

    path = tmp_path / "main.tex"
    path.write_text("Exact claim.")
    source = Source("main.tex", path, b"Exact claim.", "Exact claim.", "sources/main.tex")
    where = Location(Position("main.tex", 1, 1), Position("main.tex", 1, 13))
    claim = Claim("claim-0001", "Exact claim.", where)
    extraction = Extraction(
        {"kind": "latex", "path": "main.tex", "sha256": sha256(source.raw).hexdigest()},
        [source],
        {"A": [claim]},
    )
    validator = SimpleNamespace(
        validate=lambda c, k: Validation("unresolved", "Evidence unavailable")
    )
    report, _, _ = build_report(extraction, validator, "another_validator")
    assert report["citations"][0]["claims"][0]["validation"]["result"] == "unresolved"
    extraction.citations["A"] = [Claim("claim-0001", "Invented wording.", where)]
    with pytest.raises(ValueError, match="does not match"):
        build_report(extraction, stub, "stub")


@pytest.mark.parametrize("label,mention", [("[1]", "[1]"), ("", "Smith (2024)")])
def test_real_pdf_claims_and_page_regions(tmp_path, label, mention):
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / "research paper.PDF"
    canvas = Canvas(str(path))
    canvas.drawString(50, 700, f"Method X improves accuracy {mention}.")
    canvas.drawString(50, 650, "References")
    canvas.drawString(50, 620, f"{label} Jane Smith. Example Research. Example Journal, 2024.")
    canvas.save()
    before = path.read_bytes()
    result = run_local(path, output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert_public_contract(data, "pdf")
    assert data["citations"][0]["citation_key"] == "pdf-ref-0001"
    claim = data["citations"][0]["claims"][0]
    assert claim["claim"] == f"Method X improves accuracy {mention}."
    assert claim["location"] == {"page": 1}
    evidence = yaml.safe_load((tmp_path / "claims/.provenance/provenance.yaml").read_text())
    assert evidence["claims"][0]["location"]["pdf_regions"][0]["page"] == 1
    assert not (tmp_path / "claims/sources").exists()
    assert (
        tmp_path / "claims/.provenance/sources/original-research paper.PDF"
    ).read_bytes() == before
    assert path.read_bytes() == before


def test_unreadable_pdf_and_invalid_result_fail(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        run_local(path, output=tmp_path / "claims")
    assert not (tmp_path / "claims").exists()
    with pytest.raises(ValueError):
        Validation("true", "Stub mode.").to_dict()


def test_empty_supported_manuscript_has_no_claims(tmp_path):
    source, bib = make_project(tmp_path, "A manuscript with no citations.\n")
    result = run_local(source, bib=[bib], output=tmp_path / "claims")
    assert result["summary"]["unique_claims"] == 0
    assert result["extraction"]["state"] == "complete"


def test_normal_directory_alias_is_resolved_but_output_symlink_is_rejected(tmp_path):
    source, bib = make_project(tmp_path, "Method works\\cite{A}.")
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    result = run_local(source, bib=[bib], output=alias / "claims")
    assert Path(result["output_dir"]) == tmp_path / "claims"
    link = tmp_path / "output-link"
    link.symlink_to(tmp_path / "claims", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        run_local(source, bib=[bib], output=link)


def test_scikill_version_comes_from_installed_producer(tmp_path, monkeypatch):
    from bib_lint.claims import report

    calls = []

    def version(name):
        calls.append(name)
        return "9.8.7+test"

    monkeypatch.setattr(report, "version", version)
    source, bib = make_project(tmp_path, "Method works\\cite{A}.")
    result = run_local(source, bib=[bib], output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert_public_contract(data, "latex")
    assert data["scikill_version"] == "9.8.7+test"
    assert calls == ["sciskill"]
    assert data["document"] == {
        "kind": "latex",
        "path": "main.tex",
        "sha256": sha256(source.read_bytes()).hexdigest(),
    }


def test_version_falls_back_to_standalone_distribution(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    from bib_lint.claims import report

    def version(name):
        if name == "sciskill":
            raise PackageNotFoundError(name)
        assert name == "bib-lint"
        return "2.3.4"

    monkeypatch.setattr(report, "version", version)
    assert report.producer_version() == "2.3.4"


def test_cross_page_pdf_claim_reports_only_its_start_page(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / "paper.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(50, 700, "Background.")
    canvas.showPage()
    canvas.drawString(50, 700, "Method X improves accuracy")
    canvas.showPage()
    canvas.drawString(50, 700, "[1].")
    canvas.drawString(50, 650, "References")
    canvas.drawString(50, 620, "[1] Jane Smith. Example Research. Example Journal, 2024.")
    canvas.save()
    result = run_local(path, output=tmp_path / "claims")
    data = yaml.safe_load(Path(result["report_path"]).read_text())
    assert_public_contract(data, "pdf")
    claim = data["citations"][0]["claims"][0]
    assert claim["claim"] == "Method X improves accuracy\n[1]."
    assert claim["location"] == {"page": 2}
    evidence = yaml.safe_load((tmp_path / "claims/.provenance/provenance.yaml").read_text())
    assert {r["page"] for r in evidence["claims"][0]["location"]["pdf_regions"]} == {2, 3}
    assert "page 2" in Path(result["summary_path"]).read_text()


def test_pdf_review_findings_hide_extracted_line_column_positions(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    path = tmp_path / "paper.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(50, 700, "Background.")
    canvas.showPage()
    canvas.drawString(50, 700, "Method X improves accuracy [2].")
    canvas.drawString(50, 650, "References")
    canvas.drawString(50, 620, "[1] Jane Smith. Example Research. Example Journal, 2024.")
    canvas.save()
    result = run_local(path, output=tmp_path / "claims")
    finding = next(
        d for d in result["extraction"]["diagnostics"] if d["code"] == "unresolved_citation"
    )
    assert finding["location"] == {"page": 2}
    assert set(result["extraction"]) == {"state", "diagnostics"}
    assert "unresolved_citation: [2] (page 2)" in Path(result["summary_path"]).read_text()
    assert result["summary"]["uncertain_candidates"] == 1


def test_summary_keeps_page_lists_and_latex_finding_positions():
    from bib_lint.claims.report import finding_label

    assert finding_label(
        {"code": "image_regions", "message": "Unreadable content", "pages": [3, 16]}
    ) == ("image_regions: Unreadable content (pages 3, 16)")
    assert (
        finding_label(
            {
                "code": "needs_review",
                "message": "Ambiguous attribution",
                "location": {
                    "file": "intro.tex",
                    "start": {"line": 10, "column": 85},
                    "end": {"line": 10, "column": 157},
                },
            }
        )
        == "needs_review: Ambiguous attribution (intro.tex:10:85)"
    )
