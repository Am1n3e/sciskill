"""Real native-template PDFs through extraction and the existing scholarly verifier."""

import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from pdf_e2e.build import CACHE, FIXTURES, read_json
from pdf_e2e.isolation import pdf_only
from pdf_e2e.oracles import expand_project, normalized, rendered_text
from pdf_e2e.replay import ScholarlyReplay

from bib_lint.audit import run_audit
from bib_lint.status import reference_status
from bib_lint.verification.http import MetadataClient

pytestmark = pytest.mark.pdf_e2e


def pytest_generate_tests(metafunc):
    if "project_case" not in metafunc.fixturenames:
        return
    selected = metafunc.config.getoption("--pdf-matrix")
    if selected is None:
        metafunc.parametrize("project_case", [None])
        return
    path = FIXTURES / "renderings.json"
    if not path.exists():
        raise ValueError("Required independent rendering gold is missing")
    gold = read_json(path)
    truth = read_json(FIXTURES / "truth.json")
    cases = [expand_project(project, truth) for project in gold["projects"]]
    if selected == "pilot":
        cases = [case for case in cases if case["venue"] in {"iclr", "icml"}]
    metafunc.parametrize(
        "project_case",
        cases,
        ids=[
            case["venue"] + "/" + case["corpus"] + "/" + case["selection"]["variant"]
            for case in cases
        ],
    )


def _project_pdf(expected):
    ledger = read_json(CACHE.parent / "projects/acceptance.json")
    if not ledger.get("complete"):
        raise ValueError("Required compiled-PDF matrix is incomplete; run pdf_e2e.build --compile")
    builds = ledger["renderable_builds"] + ledger["renderable_counterparts"]
    cell = next(
        (
            cell
            for cell in builds
            if cell["venue"] == expected["venue"]
            and cell["corpus"] == expected["corpus"]
            and cell["pdf_sha256"] == expected["pdf_sha256"]
        ),
        None,
    )
    if cell is None:
        raise ValueError("No compiled PDF matches independently frozen gold")
    pdf = Path(cell["project"]) / "main.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != expected["pdf_sha256"]:
        raise ValueError("Compiled PDF differs from its reviewed rendering")
    return pdf


def _equivalent(left, right):
    return normalized(unquote(rendered_text(str(left))[0])) == normalized(
        unquote(rendered_text(str(right))[0])
    )


def _assert_fields(item, expected):
    fields = item["entry"]["fields"]
    for field in ("title", "year"):
        if field in expected["expected_fields"]:
            assert field in fields, (expected["case_id"], "missing field", field)
            assert _equivalent(fields[field], expected["expected_fields"][field]), (
                expected["case_id"],
                field,
                fields.get(field),
                expected["expected_fields"][field],
            )
    text = normalized(item["pdf"]["text"])
    for author in expected["expected_authors"]:
        if author["kind"] != "others":
            assert normalized(author["family"]) in text, (
                expected["case_id"],
                "lost author",
                author,
            )
    assert item["pdf"]["fragments"], (expected["case_id"], "missing original fragments")
    assert all(fragment["page"] >= 1 for fragment in item["pdf"]["fragments"])


def _assert_checks(item, expected):
    correctness = item["validations"]["correctness"]
    methods = correctness["methods"]
    for check in expected["required_checks"]:
        field = check["field"]
        if field in {"year", "title"} and field not in expected["expected_fields"]:
            continue
        if field == "venue" and not any(
            expected["visibility"].get(name) == "text" for name in ("journal", "booktitle")
        ):
            continue
        comparisons = [
            comparison
            for method in methods
            if check.get("source") in {None, "all_authoritative_found", method["name"]}
            for comparison in method.get("comparisons", [])
            if comparison["field"] == field
        ]
        diagnostics = [
            diagnostic
            for diagnostic in item["pdf"]["diagnostics"]
            if field in diagnostic.get("fields", [])
        ]
        assert any(c["result"] in check["results"] for c in comparisons) or (
            "unknown" in check["results"] and diagnostics
        ), (expected["case_id"], "required field finding", check, comparisons, diagnostics)
    if item["pdf"]["diagnostics"]:
        assert reference_status(item["validations"]) != "Correct"


def test_compiled_pdf_only_audits_every_rendered_reference(project_case, tmp_path, monkeypatch):
    expected = project_case
    pdf = _project_pdf(expected)
    source = tmp_path / "paper.pdf"
    shutil.copyfile(pdf, source)
    original = source.read_bytes()
    truth = read_json(FIXTURES / "truth.json")
    replay = ScholarlyReplay(truth["canonical_records"])
    output = tmp_path / "audit"
    client = MetadataClient(output / "cache", transport=httpx.MockTransport(replay))
    with pdf_only(monkeypatch, [FIXTURES, CACHE.parent / "projects"]):
        workspace, report, _ = run_audit(source, output=output, client=client)
    client.close()
    assert report["schema_version"] == 4
    assert report["verification_run"]["complete"] is True
    assert replay.unexpected == []
    assert source.read_bytes() == original
    assert json.loads(workspace.final.read_text()) == report
    cases = [case for case in expected["cases"] if case["classification"] != "omitted"]
    assert len(report["items"]) == len(cases), (
        expected["venue"],
        expected["corpus"],
        "occurrence count",
        len(report["items"]),
        len(cases),
    )
    for index, (item, case) in enumerate(zip(report["items"], cases, strict=True), 1):
        assert item["entry"]["key"] == f"pdf-ref-{index:04d}"
        _assert_fields(item, case)
        _assert_checks(item, case)
