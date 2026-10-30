"""Source-linked paper corpus, explicit mutations, and deterministic audit replays."""

import ast
import json
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from bib_lint.audit import run_audit
from bib_lint.aux import read_aux
from bib_lint.parser import BibliographyParseError, parse_file
from bib_lint.scope import validate_report
from bib_lint.status import reference_status
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.matching import compare_fields, input_record, select_result
from bib_lint.verification.providers import METHODS

ROOT = Path(__file__).parent / "fixtures/e2e"
VARIANTS = json.loads((ROOT / "rule-variants.cases.json").read_text())["cases"]
RECORDS = json.loads((ROOT / "verified-records.json").read_text())["records"]
CORE = ROOT / "representative-20.bib"
CONSENSUS_CASES = json.loads((ROOT / "consensus-cases.json").read_text())["cases"]


def paper_response(base, request):
    """Return fixed verified paper facts, never values copied from the query."""
    provider = RECORDS[base]["provider"]
    path = request.url.path
    if provider == "arxiv":
        name = "tulu" if request.url.params.get("id_list") == "2411.15124v5" else base
        return (ROOT / "evidence" / (name + ".xml")).read_text()
    if provider == "jmlr":
        title = RECORDS[base]["record"]["title"]
        if path == "/papers/":
            return '<li><a href="v22/">Volume 22</a> January 2021</li>'
        if path == "/papers/v22/":
            return f'<dl><dt>{title}</dt><dd>[<a href="20-1364.html">abs</a>]</dd></dl>'
        assert path == "/papers/v22/20-1364.html"
    elif provider == "acl_anthology":
        if path.startswith("/events/"):
            return (
                '<a href="/volumes/2025.emnlp-main/">EMNLP 2025</a>'
                if path == "/events/emnlp-2025/"
                else "<html></html>"
            )
        if path.startswith("/volumes/"):
            title = RECORDS[base]["record"]["title"]
            return f'<a href="/2025.emnlp-main.58/">{title}</a>'
        assert path == "/2025.emnlp-main.58/"
    elif provider == "openreview":
        assert path in {"/notes", "/notes/search"}
        return (ROOT / "evidence/pal_accepted.json").read_text()
    else:
        raise AssertionError(f"Unhandled replay provider: {provider}")
    return (ROOT / "evidence" / (base + ".html")).read_text()


def audit_variant(case, tmp_path, respond=None):
    calls = []

    def request(request):
        calls.append(request)
        return (
            respond(request)
            if respond
            else httpx.Response(200, text=paper_response(case["base_record"], request))
        )

    providers = list(METHODS.values()) if case["provider"] == "all" else [METHODS[case["provider"]]]
    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(request))
    try:
        workspace, report, _ = run_audit(
            ROOT / "rule-variants.bib",
            output=tmp_path / "audit",
            citation_key=case["citation_key"],
            client=client,
            methods=providers,
        )
    finally:
        client.close()
    item = next(i for i in report["items"] if i["entry"]["key"] == case["citation_key"])
    validate_report(report)
    assert workspace.checkpoint.exists()  # Other variants are intentionally pending.
    assert not report["verification_run"]["complete"]
    return item, calls


@pytest.mark.parametrize("case", VARIANTS, ids=lambda c: c["citation_key"])
def test_controlled_reference_audit(case, tmp_path):
    before = (ROOT / "rule-variants.bib").read_bytes()
    item, calls = audit_variant(case, tmp_path)
    expected = case["expected"]
    correctness = item["validations"]["correctness"]
    assert correctness["complete"]
    assert reference_status(item["validations"]) == expected["reference_status"]
    for source in correctness["methods"]:
        assert source["status"] == expected["source_status"]
        comparisons = {c["field"]: c["result"] for c in source.get("comparisons", [])}
        assert all(comparisons[k] == v for k, v in expected.get("comparisons", {}).items())
        if expected.get("rejected_candidates"):
            assert source["rejected_candidates"]
        if expected.get("error_code"):
            assert source["error"]["code"] == expected["error_code"]
    if expected.get("direct_comparisons"):
        comparisons = compare_fields(
            input_record(item["entry"]), RECORDS[case["base_record"]]["record"]
        )
        assert {c["field"]: c["result"] for c in comparisons}.items() >= expected[
            "direct_comparisons"
        ].items()
    if expected.get("unchecked_fields"):
        assert not set(expected["unchecked_fields"]) & set(correctness["checked_fields"])
    if expected.get("no_http"):
        assert not calls
    assert (ROOT / "rule-variants.bib").read_bytes() == before


@pytest.mark.parametrize(
    "provider,key,base",
    [
        ("arxiv", "gupta2024codenavtooluseusingrealworld", "codenav"),
        ("pmlr", "thomas2015hcpi", None),
        ("jmlr", "JMLR:v22:20-1364", "sb3"),
        ("acl_anthology", "you2025datawiseagentnotebookcentricllmagent", "datawise"),
        ("neurips", "kimLanguageModelsCan2023a", "kim_neurips"),
        ("openreview", "gao2022pal", "pal_accepted"),
    ],
)
def test_real_paper_provider_replay(tmp_path, provider, key, base):
    def respond(request):
        if provider == "pmlr":
            text = {
                "/": '<li><a href="v37">Volume 37</a> Proceedings of ICML 2015</li>',
                "/v37/": (ROOT.parent / "providers/pmlr-volume.html").read_text(),
                "/v37/thomas15.html": (ROOT.parent / "providers/pmlr-paper.html").read_text(),
            }[request.url.path]
        elif provider == "neurips":
            title = RECORDS[base]["record"]["title"]
            if request.url.path == "/":
                text = '<a href="/paper_files/paper/2023">2023</a>'
            elif request.url.path == "/paper_files/paper/2023":
                text = f'<a href="{RECORDS[base]["source"]}">{title}</a>'
            else:
                assert str(request.url) == RECORDS[base]["source"]
                text = (ROOT / "evidence/kim_neurips.html").read_text()
        else:
            text = paper_response(base, request)
        return httpx.Response(200, text=text)

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(
            CORE,
            output=tmp_path / "audit",
            citation_key=key,
            methods=[METHODS[provider]],
            client=client,
        )
    finally:
        client.close()
    item = next(i for i in report["items"] if i["entry"]["key"] == key)
    outcome = item["validations"]["correctness"]["methods"][0]
    assert outcome["status"] == "found" and outcome["authority"]
    assert outcome["source_url"].startswith("https://")


@pytest.mark.parametrize("case", CONSENSUS_CASES, ids=lambda c: c["id"])
def test_real_paper_consensus_scenarios(case):
    """Test shared decisions using real source facts, independently of HTTP parsing."""
    original = input_record(asdict(parse_file(CORE).entries[case["citation_key"]]))
    methods = [
        select_result(m["name"], original, m["records"], authority=m["authority"])
        if "records" in m
        else m.copy()
        for m in case["methods"]
    ]
    result = build_consensus(methods)
    expected = case["expected"]
    assert [m["status"] for m in methods] == expected["source_statuses"]
    assert reference_status({"correctness": result}) == expected["status"]
    assert result["is_correct"] is expected["is_correct"]
    canonical = result["canonical_ref"]
    assert (canonical["url"] if canonical else None) == expected["canonical_source"]
    assert result["consensus"].items() >= expected.get("consensus", {}).items()


@pytest.mark.parametrize(
    "fault,error,status",
    [
        ("denied", "access_denied", "error"),
        ("rate_limit", "rate_limited", "error"),
        ("server_error", "http_error", "error"),
        ("timeout", "network_error", "error"),
        ("malformed", "invalid_response", "error"),
        ("missing", None, "not_found"),
        ("retry_success", None, "found"),
    ],
)
def test_real_paper_transport_faults(tmp_path, fault, error, status):
    calls = []
    case = next(c for c in VARIANTS if c["citation_key"] == "case_clean")

    def respond(request):
        calls.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("Controlled timeout", request=request)
        if fault == "retry_success" and len(calls) >= 3:
            return httpx.Response(200, text=paper_response("codenav", request))
        if fault == "malformed":
            return httpx.Response(200, text="Controlled non-XML response")
        code = {
            "denied": 403,
            "rate_limit": 429,
            "server_error": 503,
            "missing": 404,
            "retry_success": 503,
        }[fault]
        return httpx.Response(code, headers={"Retry-After": "1000"} if code == 429 else {})

    item, _ = audit_variant(case, tmp_path, respond)
    source = item["validations"]["correctness"]["methods"][0]
    assert source["status"] == status
    if error:
        assert source["error"]["code"] == error
    assert reference_status(item["validations"]) == (
        "Correct" if fault == "retry_success" else "Unresolved"
    )
    assert len(calls) <= 3


@pytest.mark.parametrize(
    "name",
    ["malformed", "duplicate-keys", "duplicate-fields", "undefined-macro", "invalid-author"],
)
def test_corpus_parser_rejections(name):
    with pytest.raises(BibliographyParseError):
        parse_file(ROOT / "parser" / (name + ".bib"))


def test_corpus_encoding_macros_empty_and_custom_fields():
    path = ROOT / "parser/latin1.bib"
    original = path.read_bytes()
    with pytest.raises(BibliographyParseError):
        parse_file(path)
    assert (
        parse_file(path, encoding="latin-1").entries["encoding_control"].fields["title"] == "Café"
    )
    assert path.read_bytes() == original
    assert not parse_file(ROOT / "parser/empty.bib").entries
    bib = parse_file(ROOT / "parser/macros.bib")
    assert bib.preambles
    assert bib.entries["macro_control"].fields == {
        "title": "CodeNav",
        "year": "2024",
        "customfield": "Keep me",
        "crossref": "parent",
    }


def test_corpus_aux_scope_and_nested_cycles(tmp_path):
    _, report, warnings = run_audit(
        CORE, output=tmp_path / "audit", aux=ROOT / "aux/selected.aux", preview=True
    )
    assert set(report["verification_scope"]["eligible_keys"]) == {
        "gupta2024codenavtooluseusingrealworld",
        "JMLR:v22:20-1364",
    }
    assert not warnings
    nested = read_aux(ROOT / "aux/paper.aux")
    assert nested.keys == {"GUPTA2024CODENAVTOOLUSEUSINGREALWORLD", "missing-control"}
    assert len(nested.files) == 2
    _, nested_report, warnings = run_audit(
        CORE, output=tmp_path / "nested", aux=ROOT / "aux/paper.aux", preview=True
    )
    assert nested_report["verification_scope"]["eligible_keys"] == [
        "gupta2024codenavtooluseusingrealworld"
    ]
    assert warnings == ["Missing citation keys: missing-control"]
    assert read_aux(ROOT / "aux/all.aux").keys == {"*"}
    assert not read_aux(ROOT / "aux/none.aux").keys


@pytest.mark.parametrize("name", ["malformed", "biblatex", "missing-input"])
def test_corpus_aux_rejections(name):
    with pytest.raises((ValueError, FileNotFoundError)):
        read_aux(ROOT / "aux" / (name + ".aux"))


def test_coverage_matrix_has_a_witness_and_test_for_every_rule():
    matrix = json.loads((ROOT / "coverage-matrix.json").read_text())
    core = parse_file(CORE)
    variants = parse_file(ROOT / "rule-variants.bib")
    assert len(core.entries) == 20
    assert len(variants.entries) == len(VARIANTS) == 31
    assert set(core.entries) == {
        c["citation_key"] for c in json.loads(CORE.with_suffix(".cases.json").read_text())["cases"]
    }
    assert {e.type for e in core.entries.values()} == {"book", "article", "inproceedings", "misc"}
    scenarios = {s["id"]: s for s in matrix["scenarios"]}
    assert len(scenarios) == len(matrix["scenarios"])
    assert len({r["id"] for r in matrix["rules"]}) == len(matrix["rules"])
    witnesses = {w for rule in matrix["rules"] for w in rule["witnesses"]}
    assert {"variant:" + key for key in variants.entries} <= witnesses
    assert {case["id"] for case in CONSENSUS_CASES} <= {r["id"] for r in matrix["rules"]}
    for rule in matrix["rules"]:
        assert rule["coverage_layer"] in matrix["coverage_layers"]
        assert rule["witnesses"] and rule["tests"], rule["id"]
        for witness in rule["witnesses"]:
            kind, key = witness.split(":", 1)
            if kind == "reference":
                assert key in core.entries
            elif kind == "variant":
                assert key in variants.entries
            elif kind == "scenario":
                assert key in scenarios
                assert scenarios[key]["reference"] in core.entries
            else:
                assert kind == "file" and (ROOT / key).is_file()
        for test in rule["tests"]:
            path, function = test.split("::")[:2]
            module = ast.parse((Path(__file__).parent / path).read_text())
            assert any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function
                for n in module.body
            ), test
    assert all(RECORDS[key]["source"].startswith("https://") for key in RECORDS)
