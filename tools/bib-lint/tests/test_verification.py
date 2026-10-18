import copy
import json

import httpx
import pytest
from provider_support import fixture_registry
from support import ENTRY, RECORD, FakeClient

from bib_lint.verification import verify_file, verify_reference
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.matching import compare_fields, input_record, normalize, select_result


def method(name="crossref", record=None, authority=True, original=None):
    return select_result(
        name, original or RECORD, [record or copy.deepcopy(RECORD)], authority=authority
    )


def test_correct_and_discrepancy():
    result = build_consensus([method(), method("openalex", authority=False)])
    assert result["is_correct"] is True
    assert "status" not in result
    assert result["consensus"]["display"] == "2/2"
    changed = {**RECORD, "year": 2024}
    result = build_consensus([method(record=changed)])
    assert result["is_correct"] is False
    assert result["methods"][0]["differences"][0]["field"] == "year"


def test_shared_error_is_not_truth():
    assert (
        build_consensus(
            [method("openalex", authority=False), method("semantic_scholar", authority=False)]
        )["is_correct"]
        is None
    )


def test_conflicting_authoritative_years():
    result = build_consensus([method(), method("publisher", record={**RECORD, "year": 2024})])
    assert result["is_correct"] is None
    assert "conflict" in result["reason"]


def test_wrong_doi_does_not_establish_identity():
    wrong = {**RECORD, "title": "An Unrelated Study of Stellar Evolution"}
    assert method(record=wrong)["status"] == "not_found"


def test_two_versions_ambiguous():
    second = {**RECORD, "identifiers": {"doi": "10.1234/other"}}
    result = select_result("crossref", RECORD, [RECORD, second], authority=True)
    assert result["status"] == "ambiguous"
    assert build_consensus([result])["is_correct"] is None


def test_versions_from_authorities_not_voted_away():
    second = {**RECORD, "identifiers": {"arxiv": "2501.12345v1"}, "venue": "arXiv", "year": 2024}
    result = build_consensus(
        [method(), method("openalex", authority=False), method("arxiv", record=second)]
    )
    assert result["is_correct"] is None


def test_unavailable_and_not_applicable_denominator():
    result = build_consensus(
        [
            method(),
            {"name": "x", "status": "error"},
            {"name": "publisher", "status": "not_applicable"},
        ]
    )
    assert result["consensus"]["display"] == "1/1"
    assert result["consensus"]["unavailable"] == 1
    assert result["consensus"]["disagree"] == 0


def test_given_names_and_incomplete_metadata():
    missing = {**RECORD, "authors": []}
    assert build_consensus([method(record=missing)])["is_correct"] is None
    initials = {**RECORD, "authors": [{"given": "J.", "family": "Smith"}]}
    assert build_consensus([method(record=initials)])["is_correct"] is None
    wrong = {**RECORD, "authors": [{"given": "Zora", "family": "Smith"}]}
    assert build_consensus([method(record=wrong)])["is_correct"] is False
    assert normalize(r"Garc{\'i}a") == normalize("García")


def test_all_adapters_run_after_failure():
    calls = []

    def fail(record, client):
        calls.append("fail")
        raise LookupFailure("rate_limited", "Rate limit")

    def succeed(record, client):
        calls.append("succeed")
        return method()

    result = verify_reference(
        ENTRY, FakeClient(), methods=fixture_registry({"failed": fail, "crossref": succeed})
    )
    assert calls == ["fail", "succeed"]
    assert result["methods"][0]["error"]["code"] == "rate_limited"
    assert result["is_correct"] is True


def test_cache_redacts_credentials(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"title": "Example"})

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    for _ in range(2):
        assert (
            client.json("https://api.openalex.org/works", params={"api_key": "SECRET"})["title"]
            == "Example"
        )
    client.close()
    assert len(calls) == 1
    assert client.evidence[-1]["cached"] is True
    assert "SECRET" not in next(tmp_path.glob("*.json")).read_text()
    assert "SECRET" not in json.dumps(client.evidence)


def test_rate_limit_is_bounded(tmp_path):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "1000"})
        ),
    )
    with pytest.raises(LookupFailure, match="rate limit"):
        client.get("https://api.crossref.org/works")
    client.close()


def test_verify_report_preserves_input_and_validations(tmp_path):
    source = tmp_path / "refs.tmp.json"
    report = {
        "schema_version": 2,
        "summary": {"total_count": 1, "total_not_used": 0},
        "items": [{"entry": ENTRY, "validations": {"is_used": True}}],
    }
    source.write_text(json.dumps(report))
    original = source.read_bytes()
    output, summary = verify_file(
        source, client=FakeClient(), methods=fixture_registry({"crossref": lambda r, c: method()})
    )
    data = json.loads(output.read_text())
    assert data["items"][0]["entry"] == ENTRY
    assert data["items"][0]["validations"]["is_used"] is True
    assert data["items"][0]["validations"]["correctness"]["is_correct"] is True
    assert summary == {
        "correct": 1,
        "incorrect": 0,
        "unresolved": 0,
        "partial_match": 0,
        "needs_review": 0,
        "method_errors": 0,
        "skipped_unused": 0,
    }
    assert not source.exists()
    assert json.loads(original)["items"][0]["entry"] == data["items"][0]["entry"]


def test_invalid_input_does_not_replace_output(tmp_path):
    source = tmp_path / "refs.json"
    source.write_text('{"items": []}')
    output = tmp_path / "out.json"
    output.write_text("old")
    with pytest.raises(ValueError, match="schema"):
        verify_file(source, output=output)
    assert output.read_text() == "old"


def test_identifiers_from_journal_and_url():
    entry = copy.deepcopy(ENTRY)
    entry["fields"] = {"title": "Title", "journal": "arXiv preprint arXiv:2411.15124"}
    assert input_record(entry)["identifiers"]["arxiv"] == "2411.15124"
    assert input_record(entry)["record_type"] == "preprint"
    entry["fields"] = {"title": "Title", "url": "https://doi.org/10.1234/example"}
    assert input_record(entry)["identifiers"] == {"doi": "10.1234/example"}


def test_preprint_year_does_not_disprove_publication_year():
    preprint = {**RECORD, "record_type": "preprint", "year": 2024, "venue": "arXiv"}
    result = build_consensus([method("arxiv", record=preprint)])
    assert result["is_correct"] is None


def test_arxiv_unversioned_input_accepts_versioned_record():
    original = {
        **RECORD,
        "record_type": "preprint",
        "venue": "arXiv preprint arXiv:2501.12345",
        "identifiers": {"arxiv": "2501.12345"},
    }
    found = {**original, "venue": "arXiv", "identifiers": {"arxiv": "2501.12345v1"}}
    result = build_consensus([method("arxiv", record=found, original=original)])
    assert result["is_correct"] is True
    assert result["methods"][0]["comparisons"][-1]["found"] == "2501.12345v1"


def test_http_error_includes_server_message(tmp_path):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                406,
                text="<html><body>Unsupported request format</body></html>",
                headers={"Content-Type": "text/html"},
            )
        ),
    )
    with pytest.raises(
        LookupFailure, match="HTTP 406: Not Acceptable — Unsupported request format"
    ):
        client.get("https://export.arxiv.org/api/query")
    client.close()


def test_http_error_redacts_credentials_and_bounds_output(tmp_path):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, text="Rejected SECRET\n" + "x" * 1000)
        ),
    )
    with pytest.raises(LookupFailure) as error:
        client.get("https://api.openalex.org/works", params={"api_key": "SECRET"})
    assert "SECRET" not in str(error.value)
    assert "[redacted]" in str(error.value)
    assert len(str(error.value)) < 550
    client.close()


def test_empty_http_error_body_uses_reason(tmp_path):
    client = MetadataClient(tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(406)))
    with pytest.raises(LookupFailure, match="HTTP 406: Not Acceptable"):
        client.get("https://export.arxiv.org/api/query")
    client.close()


def test_title_difference_is_mismatch_but_missing_title_is_unknown():
    original = {
        **RECORD,
        "title": 'T{"u}lu 3: Pushing Frontiers in Open Language Model Post-Training',
    }
    found = {**RECORD, "title": "Tulu 3: Pushing Frontiers in Open Language Model Post-Training"}
    assert compare_fields(original, found)[0]["result"] == "mismatch"
    result = build_consensus([method("arxiv", record=found, original=original)])
    assert result["is_correct"] is False
    assert compare_fields(original, {**found, "title": None})[0]["result"] == "unknown"
    assert compare_fields(RECORD, RECORD)[0]["result"] == "match"


def test_default_sources_are_six_approved_providers():
    from bib_lint.verification.providers import METHODS

    assert set(METHODS) == {"arxiv", "pmlr", "jmlr", "acl_anthology", "neurips", "openreview"}


def test_abbreviated_authors_partial_match_and_wrong_prefix():
    from bib_lint.status import reference_status

    original = copy.deepcopy(RECORD)
    original["authors"].append({"family": "others"})
    found = copy.deepcopy(RECORD)
    found["authors"].append({"given": "John", "family": "Doe"})
    source = method("arxiv", record=found, original=original)
    assert source["comparisons"][1]["result"] == "partial_match"
    decision = build_consensus([source])
    assert reference_status({"correctness": decision}) == "Partial match"
    assert decision["is_correct"] is None
    original["authors"][0]["family"] = "Wrong"
    assert compare_fields(original, found)[1]["result"] == "mismatch"


def test_found_but_incomplete_is_needs_review_not_unresolved():
    from bib_lint.status import reference_status

    decision = build_consensus([method("openalex", authority=False)])
    assert reference_status({"correctness": decision}) == "Needs review"
    assert reference_status({"correctness": build_consensus([])}) == "Unresolved"
