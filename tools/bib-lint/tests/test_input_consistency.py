"""Regression checks for metadata discarded by routing/field precedence."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from bib_lint.parser import parse_file
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import select_result
from bib_lint.verification.providers.protocol import LookupQuery

ROOT = Path(__file__).parent / "fixtures/e2e"
SOURCES = json.loads((ROOT / "adversarial.sources.json").read_text())["records"]
BIB = ROOT / "adversarial.bib"


def evaluate(key, base):
    entry = asdict(parse_file(BIB).entries[key])
    query = LookupQuery.from_entry(entry)
    method = select_result("primary", query.as_record(), [SOURCES[base]["record"]], authority=True)
    return query, build_consensus([method])


@pytest.mark.parametrize(
    "key,base,field",
    [
        ("adv_match_arxiv_concatenated_identifiers", "codenav", "arxiv"),
        ("adv_match_arxiv_double_version", "codenav", "arxiv"),
        ("adv_match_arxiv_foreign_url_identifier", "codenav", "arxiv"),
        ("adv_provider_split_arxiv_url", "codenav", "arxiv"),
        ("adv_provider_shadowed_version_pin", "codenav", "arxiv"),
        ("adv_provider_shadowed_journal_id", "codenav", "arxiv"),
        ("adv_provider_acl_alias_conflict", "datawise", "acl"),
        ("adv_provider_openreview_alias_conflict", "pal_accepted", "openreview"),
        ("adv_provider_duplicate_forum_id", "pal_accepted", "openreview"),
        ("adv_provider_pmlr_alias_conflict", "hcpi", "pmlr"),
        ("adv_consensus_shadowed_booktitle", "datawise", "venue"),
    ],
)
def test_secondary_metadata_cannot_disappear(key, base, field):
    query, result = evaluate(key, base)
    assert result["is_correct"] is not True
    checks = result["methods"][0]["comparisons"]
    assert any(c["field"] == field and c["result"] in {"unknown", "mismatch"} for c in checks)
    assert query.as_record()["input_fields"] == dict(query.fields)


@pytest.mark.parametrize("token", ["2406.12276v1garbage", "2406.12276v0", "2406.12276v1v2"])
def test_whole_eprint_token_is_checked(token):
    entry = asdict(parse_file(BIB).entries["adv_provider_split_arxiv_url"])
    entry["fields"].update(url="https://arxiv.org/abs/2406.12276v1", eprint=token)
    query = LookupQuery.from_entry(entry)
    method = select_result(
        "arxiv", query.as_record(), [SOURCES["codenav"]["record"]], authority=True
    )
    assert build_consensus([method])["is_correct"] is not True
    assert any(c.get("code") == "invalid_identifier" for c in method["comparisons"])


def test_explicit_provider_alias_is_compared_after_title_fallback():
    entry = asdict(parse_file(BIB).entries["adv_provider_acl_alias_conflict"])
    entry["fields"].pop("url")
    query = LookupQuery.from_entry(entry)
    method = select_result(
        "acl_anthology", query.as_record(), [SOURCES["datawise"]["record"]], authority=True
    )
    assert build_consensus([method])["is_correct"] is False
    assert any(c["field"] == "acl" and c["result"] == "mismatch" for c in method["comparisons"])


def test_doi_url_cannot_be_shadowed_by_a_correct_doi_field():
    entry = asdict(parse_file(BIB).entries["adv_provider_acl_alias_conflict"])
    entry["fields"].pop("acl_id")
    entry["fields"]["url"] = "https://doi.org/10.18653/v1/2024.acl-long.505"
    method = select_result(
        "acl_anthology",
        LookupQuery.from_entry(entry).as_record(),
        [SOURCES["datawise"]["record"]],
        authority=True,
    )
    assert build_consensus([method])["is_correct"] is not True
    assert any(c["field"] == "doi" and c["result"] != "match" for c in method["comparisons"])


@pytest.mark.parametrize(
    "token", ["arXiv:2406.12276v1", "ARXIV: 2406.12276v1", "https://arxiv.org/pdf/2406.12276v1.pdf"]
)
def test_valid_arxiv_wrappers_remain_valid(token):
    entry = asdict(parse_file(BIB).entries["adv_match_clean_unicode_decomposed"])
    entry["fields"].update(eprint=token, url="https://arxiv.org/abs/2406.12276v1")
    from bib_lint.verification.input_checks import input_findings

    assert not input_findings(entry["fields"])


def test_input_diagnostic_preserves_known_source_value():
    _, result = evaluate("adv_match_arxiv_double_version", "codenav")
    comparison = next(c for c in result["methods"][0]["comparisons"] if c["field"] == "arxiv")
    assert comparison["found"] == "2406.12276v1"
    assert comparison["input_findings"]


@pytest.mark.parametrize("value", ["https://[", "arxiv.org/abs/2406.12276v1"])
def test_malformed_url_cannot_disappear(value):
    from bib_lint.verification.input_checks import input_findings

    findings = input_findings({"url": value, "eprint": "2406.12276v1"})
    assert any(c["field"] == "url" for c in findings)


def test_advertised_neurips_pdf_is_a_valid_source_locator():
    from bib_lint.verification.input_checks import input_findings

    url = (
        "https://proceedings.neurips.cc/paper_files/paper/2023/file/"
        "7cc1005ec73cfbaac9fa21192b622507-Paper-Conference.pdf"
    )
    assert not input_findings({"url": url})


@pytest.mark.parametrize("unavailable", [False, True])
def test_other_primary_cannot_hide_unverified_secondary_locator(tmp_path, unavailable):
    import httpx

    from bib_lint.status import reference_status
    from bib_lint.verification import verify_reference
    from bib_lint.verification.http import MetadataClient
    from evaluation.adversarial import FixedPaperWorld

    entry = asdict(parse_file(BIB).entries["adv_flow_CodeNav/../%2E%2E"])
    entry["fields"]["acl_id"] = "2025.emnlp-main.58"
    world = FixedPaperWorld()

    def respond(request):
        if unavailable and request.url.host == "aclanthology.org":
            return httpx.Response(503)
        return world(request)

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        result = verify_reference(entry, client)
    finally:
        client.close()
    assert reference_status({"correctness": result}) == "Needs review"
    assert any(
        c["field"] == "acl" and c["code"] in {"unverified_identifier", "locator_identity_mismatch"}
        for c in result["input_findings"]
    )
    assert next(m for m in result["methods"] if m["name"] == "arxiv")["status"] == "found"


def test_verified_unqualified_secondary_note_does_not_discredit_primary(tmp_path):
    import httpx

    from bib_lint.verification import verify_reference
    from bib_lint.verification.http import MetadataClient
    from evaluation.adversarial import FixedPaperWorld

    entry = asdict(parse_file(BIB).entries["adv_consensus_datawise_primary_control"])
    entry["fields"]["openreview_id"] = "gy7fpSzJqz"
    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(FixedPaperWorld()))
    try:
        result = verify_reference(entry, client)
    finally:
        client.close()
    assert result["is_correct"] is True
    assert not result["input_findings"]


def test_advertised_pmlr_nested_pdf_is_a_valid_source_locator():
    from bib_lint.verification.input_checks import input_findings, locator

    # This exact URL is advertised by the original World of Bits paper's metadata.
    url = "http://proceedings.mlr.press/v70/shi17a/shi17a.pdf"
    assert not input_findings({"url": url})
    assert locator("pmlr", "v70/shi17a/shi17a.pdf") == "v70/shi17a"
    assert locator("pmlr", "v70/shi17a/other.pdf") is None
