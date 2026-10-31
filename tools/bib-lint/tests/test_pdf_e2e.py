"""Real native-template PDFs through extraction and the existing scholarly verifier."""

import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from pdf_e2e.assets import VENDORED_ROOT
from pdf_e2e.build import CACHE, FIXTURES, read_json
from pdf_e2e.isolation import pdf_only
from pdf_e2e.issues import assert_locator_issue
from pdf_e2e.oracles import (
    _locator_visible,
    equivalent_text,
    expand_project,
    normalized,
    validate_gold_inventory,
)
from pdf_e2e.replay import ScholarlyReplay

from bib_lint.cli import main
from bib_lint.status import reference_status
from bib_lint.verification.http import MetadataClient

pytestmark = pytest.mark.pdf_e2e
PROTECTED_INPUTS = (FIXTURES, CACHE.parent / "projects", VENDORED_ROOT)


def pytest_generate_tests(metafunc):
    if "project_case" not in metafunc.fixturenames:
        return
    selected = metafunc.config.getoption("--pdf-matrix")
    if selected is None:
        metafunc.parametrize("project_case", [None])
        return
    path = FIXTURES / ("stress-renderings.json" if selected == "stress" else "renderings.json")
    if not path.exists():
        raise ValueError("Required independent rendering gold is missing")
    gold = read_json(path)
    ledger = read_json(
        CACHE.parent / "projects" / ("stress.json" if selected == "stress" else "acceptance.json")
    )
    validate_gold_inventory(gold, ledger)
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
    stress = expected["selection"]["variant"].startswith("stress-")
    ledger = read_json(CACHE.parent / "projects" / ("stress.json" if stress else "acceptance.json"))
    if not ledger.get("complete"):
        raise ValueError("Required compiled-PDF matrix is incomplete; run pdf_e2e.build --compile")
    builds = (
        ledger["builds"]
        if stress
        else ledger["renderable_builds"] + ledger["renderable_counterparts"]
    )
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


def _equivalent(left, right, fragments=()):
    return equivalent_text(unquote(str(left)), unquote(str(right)), list(fragments))


def _assert_anchor(item, expected):
    anchor = expected["anchor"]
    fragments = item["pdf"]["fragments"]
    first = fragments[0]
    assert first["page"] == anchor["page"], (
        expected["case_id"],
        "physical first page",
        first,
        anchor,
    )
    line = [
        fragment
        for fragment in fragments
        if fragment["page"] == first["page"] and abs(fragment["top"] - first["top"]) < 2
    ]
    box = [
        min(f["x0"] for f in line),
        min(f["top"] for f in line),
        max(f["x1"] for f in line),
        max(f["bottom"] for f in line),
    ]
    assert all(abs(actual - gold) < 2 for actual, gold in zip(box, anchor["box"], strict=True)), (
        expected["case_id"],
        "physical first-line box",
        box,
        anchor["box"],
    )


def _assert_fields(item, expected):
    fields = item["entry"]["fields"]
    if expected["expected_authors"] and all(
        author["kind"] == "others" for author in expected["expected_authors"]
    ):
        assert any(
            diagnostic.get("code") == "missing_authors"
            and "authors" in diagnostic.get("fields", [])
            for diagnostic in item["pdf"].get("diagnostics", [])
        ), (expected["case_id"], "missing_authors diagnostic for an others-only author list")
    if "doi" in expected["expected_fields"] and not any(
        issue.get("requirement") == "typeset_nested_doi_url"
        for issue in expected.get("required_issues", [])
    ):
        printed = expected["expected_fields"]["doi"]
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", printed, flags=re.I)
        actual = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", fields.get("doi", ""), flags=re.I)
        assert _equivalent(actual, doi, item["pdf"]["fragments"]), (
            expected["case_id"],
            "complete printed doi",
            fields.get("doi"),
            doi,
        )
    for field in expected.get("absent_fields", []):
        assert not fields.get(field), (
            expected["case_id"],
            "unprinted field was fabricated",
            field,
            fields[field],
        )
    for field in ("title", "year"):
        if field in expected["expected_fields"]:
            assert field in fields, (expected["case_id"], "missing field", field)
            assert _equivalent(
                fields[field], expected["expected_fields"][field], item["pdf"]["fragments"]
            ), (
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
    if expected.get("author_structure_visible", True) and not any(
        author["kind"] == "literal" for author in expected["expected_authors"]
    ):
        people = item["entry"]["persons"].get("author", [])
        assert len(people) == len(expected["expected_authors"]), (
            expected["case_id"],
            "structured author count",
            people,
            expected["expected_authors"],
        )
        for actual, author in zip(people, expected["expected_authors"], strict=True):
            assert _equivalent(
                " ".join(actual.get("first", []) + actual.get("middle", [])),
                author["given"],
                item["pdf"]["fragments"],
            ), (expected["case_id"], "given name", actual, author)
            assert _equivalent(
                " ".join(actual.get("prelast", []) + actual.get("last", [])),
                author["family"],
                item["pdf"]["fragments"],
            ), (expected["case_id"], "family name", actual, author)
            assert _equivalent(
                " ".join(actual.get("lineage", [])), author["suffix"], item["pdf"]["fragments"]
            ), (
                expected["case_id"],
                "name suffix",
                actual,
                author,
            )
    assert item["pdf"]["fragments"], (expected["case_id"], "missing original fragments")
    assert all(fragment["page"] >= 1 for fragment in item["pdf"]["fragments"])


def _assert_primary_check(methods, check, expected):
    primary = [
        method for method in methods if method.get("authority") and method["status"] == "found"
    ]
    assert primary and all(
        any(
            comparison["field"] == check["field"] and comparison["result"] in check["results"]
            for comparison in method.get("comparisons", [])
        )
        for method in primary
    ), (expected["case_id"], "all authoritative field findings", check, primary)
    if expected.get("primary_sources"):
        assert {method["name"] for method in primary} == set(expected["primary_sources"]), (
            expected["case_id"],
            "all authoritative sources found",
            primary,
            expected["primary_sources"],
        )


def _assert_candidate_review(item, expected):
    if not expected.get("candidate_review"):
        return
    target = expected["candidate_review"]
    correctness = item["validations"]["correctness"]
    assert any(
        finding.get("field") == "title"
        and finding.get("code") == "candidate_title_discrepancy"
        and finding.get("result") == "unknown"
        and _equivalent(finding.get("input"), target["input"], item["pdf"]["fragments"])
        and _equivalent(finding.get("found"), target["found"])
        for finding in correctness.get("input_findings", [])
    ), (expected["case_id"], "precise candidate title review", target)
    assert correctness.get("canonical_ref") is None, (
        expected["case_id"],
        "candidate identity remains unselected",
    )
    assert any(
        method["name"] == target["source"]
        and method["status"] == "not_found"
        and not method.get("found_ref")
        and any(
            _equivalent(candidate.get("title"), target["found"])
            for candidate in method.get("rejected_candidates", [])
        )
        for method in correctness["methods"]
    ), (expected["case_id"], "candidate remains rejected", target)


def _assert_checks(item, expected):
    correctness = item["validations"]["correctness"]
    methods = correctness["methods"]
    _assert_candidate_review(item, expected)
    for check in expected["required_checks"]:
        field = check["field"]
        if field == "title" and expected.get("candidate_review"):
            continue  # Exact disputed input/found evidence is checked above; identity was erased.
        if field in {"arxiv", "doi", "pmlr", "jmlr", "acl", "openreview"} and not _locator_visible(
            field, expected["visibility"]
        ):
            continue
        if field in {"year", "title"} and field not in expected["expected_fields"]:
            continue
        if field == "venue" and not any(
            expected["visibility"].get(name) == "text" for name in ("journal", "booktitle")
        ):
            continue
        if check.get("source") == "all_authoritative_found":
            _assert_primary_check(methods, check, expected)
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
    for issue in expected.get("required_issues", []):
        assert_locator_issue(item, issue, expected)
    if expected["expected_statuses"]:
        assert reference_status(item["validations"]) in expected["expected_statuses"], (
            expected["case_id"],
            "verdict",
            reference_status(item["validations"]),
            expected["expected_statuses"],
            correctness.get("reason"),
        )
    if item["pdf"]["diagnostics"]:
        assert reference_status(item["validations"]) != "Correct"


def test_compiled_pdf_only_audits_every_rendered_reference(
    project_case, tmp_path, monkeypatch, capsys
):
    expected = project_case
    pdf = _project_pdf(expected)
    source = tmp_path / "paper.pdf"
    shutil.copyfile(pdf, source)
    original = source.read_bytes()
    truth = read_json(FIXTURES / "truth.json")
    replay = ScholarlyReplay(truth["canonical_records"])
    output = tmp_path / "audit"
    original_init = MetadataClient.__init__

    def with_transport(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(replay)
        original_init(self, *args, **kwargs)

    with monkeypatch.context() as transport_patch:
        transport_patch.setattr(MetadataClient, "__init__", with_transport)
        with pdf_only(monkeypatch, PROTECTED_INPUTS) as guarded:
            code = main(["verify", str(source), "--output", str(output), "--json"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == 0, envelope
    assert len(guarded) == 1, (
        "Every actual isolated parser worker must receive the input/network guard"
    )
    assert envelope["status"] == "completed"
    report_path = Path(envelope["report_path"])
    report = read_json(report_path)
    debug = CACHE.parent / "product-reports"
    debug.mkdir(exist_ok=True)
    (
        debug
        / (
            expected["venue"]
            + "-"
            + expected["corpus"]
            + "-"
            + expected["pdf_sha256"][:12]
            + ".json"
        )
    ).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    assert report["schema_version"] == 4
    assert report["extraction"]["document"]["pages"] == expected["pages"]
    assert report["verification_run"]["complete"] is True
    assert replay.unexpected == []
    assert source.read_bytes() == original
    assert report_path == output / "report.json"
    cases = [case for case in expected["cases"] if case["classification"] != "omitted"]
    assert len(report["items"]) == len(cases), (
        expected["venue"],
        expected["corpus"],
        "occurrence count",
        len(report["items"]),
        len(cases),
    )
    failures = []
    for index, (item, case) in enumerate(zip(report["items"], cases, strict=True), 1):
        assert item["entry"]["key"] == f"pdf-ref-{index:04d}"
        for check in (_assert_fields, _assert_anchor, _assert_checks):
            try:
                check(item, case)
            except AssertionError as error:
                failures.append(str(error))
    assert not failures, "\n".join(failures)
