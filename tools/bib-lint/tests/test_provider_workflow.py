import copy
import json
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from provider_support import FixtureProvider
from support import ENTRY, FakeClient

from bib_lint.audit import run_audit
from bib_lint.scope import validate_report
from bib_lint.storage import report_lock, write_json
from bib_lint.verification import verify_file, verify_reference
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.protocol import (
    Applicability,
    Candidate,
    LookupAttempt,
    LookupResult,
)

PAYLOAD = {
    "heading": "An Example Paper",
    "people": [{"given": "Jane", "family": "Smith"}],
    "date": "2025",
    "journal": "Example Journal",
    "ids": {"doi": "10.1234/example"},
}


@pytest.fixture
def bib(tmp_path):
    path = tmp_path / "refs.bib"
    path.write_text(
        "@article{Example,title={An Example Paper},author={Jane Smith},year={2025},"
        "journal={Example Journal},doi={10.1234/example}}"
    )
    return path


def test_duplicate_and_invalid_registry_before_writes(bib, tmp_path):
    p = FixtureProvider(payload=PAYLOAD)
    output = tmp_path / "audit"
    with pytest.raises(ValueError, match="Duplicate"):
        run_audit(bib, output=output, methods=[p, p], client=FakeClient())
    assert not output.exists()
    path = tmp_path / "input.json"
    path.write_text(
        json.dumps(
            {"schema_version": 2, "items": [{"entry": ENTRY, "validations": {"is_used": True}}]}
        )
    )
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Duplicate"):
        verify_file(path, methods=[p, p], client=FakeClient())
    assert path.read_bytes() == original
    p.descriptor = replace(
        p.descriptor, request_policy=replace(p.descriptor.request_policy, max_pages=0)
    )
    with pytest.raises(ValueError, match="policy"):
        run_audit(bib, output=output, methods=[p], client=FakeClient())
    assert not output.exists()


def test_seventh_provider_audit_checkpoint_resume_and_json(bib):
    p = FixtureProvider(payload=PAYLOAD)
    workspace, report, _ = run_audit(bib, methods=[p], client=FakeClient())
    assert report["items"][0]["validations"]["correctness"]["is_correct"] is True
    assert report["verification_run"]["provider_protocol_version"] == 1
    assert report["verification_run"]["orchestration_version"] == 6
    assert report["verification_run"]["policy_version"] == 8
    assert report["verification_run"]["providers"] == [p.descriptor.serialize()]
    assert json.loads(workspace.final.read_text()) == json.loads(json.dumps(report))
    p.retrieval = lambda *_: pytest.fail("Compatible completed source rerun")
    _, resumed, _ = run_audit(bib, methods=[p], client=FakeClient())
    assert resumed["items"][0]["validations"] == report["items"][0]["validations"]


@pytest.mark.parametrize("phase", ["read", "write"])
def test_cache_lock_failure_aborts_audit_without_saving_source_failure(bib, tmp_path, phase):
    output = tmp_path / "audit"
    cache = output / "cache"
    cache.mkdir(parents=True)
    calls = []

    def lookup(query, context):
        context.get("https://fixture.test/paper")
        return FixtureProvider(payload=PAYLOAD).lookup(query, context)

    provider = FixtureProvider(lookup=lookup)
    with ExitStack() as stack:

        def respond(request):
            calls.append(request)
            if phase == "write":
                stack.enter_context(report_lock(cache / "checksum.json"))
            return httpx.Response(200, text="Saved source")

        client = MetadataClient(cache, transport=httpx.MockTransport(respond))
        stack.callback(client.close)
        if phase == "read":
            stack.enter_context(report_lock(cache / "checksum.json"))
        with pytest.raises(ValueError, match="already in use"):
            run_audit(bib, output=output, methods=[provider], client=client)
    assert len(calls) == (0 if phase == "read" else 1)
    assert not (output / "report.json").exists()
    checkpoint = json.loads((output / "report.tmp.json").read_text())
    assert "correctness" not in checkpoint["items"][0]["validations"]
    client = MetadataClient(
        cache, transport=httpx.MockTransport(lambda _: httpx.Response(200, text="Saved source"))
    )
    try:
        _, resumed, _ = run_audit(bib, output=output, methods=[provider], client=client)
        assert resumed["verification_run"]["complete"]
        assert resumed["items"][0]["validations"]["correctness"]["is_correct"] is True
    finally:
        client.close()


def test_v2_misclassified_lock_failure_is_rechecked_on_resume(bib):
    def legacy_failure(*_):
        raise ValueError("Report is already in use: checksum.json")

    provider = FixtureProvider(lookup=legacy_failure)
    workspace, report, _ = run_audit(bib, methods=[provider], client=FakeClient())
    assert report["items"][0]["validations"]["correctness"]["methods"][0]["error"] == {
        "code": "invalid_response",
        "message": "ValueError",
    }
    report["verification_run"]["orchestration_version"] = 2
    write_json(workspace.final, report)
    provider.retrieval = None
    provider.payload = PAYLOAD
    _, resumed, _ = run_audit(bib, methods=[provider], client=FakeClient())
    assert resumed["items"][0]["validations"]["correctness"]["is_correct"] is True


@pytest.mark.parametrize("change", ["revision", "policy", "configuration", "order"])
def test_descriptor_change_invalidates_all_decisions_preserving_final(bib, change):
    bib.write_text(
        bib.read_text()
        + "\n@article{Other,title={An Example Paper},author={Jane Smith},year={2025},"
        "journal={Example Journal},doi={10.1234/example}}"
    )
    providers = [
        FixtureProvider("first", payload=PAYLOAD),
        FixtureProvider("second", payload=PAYLOAD),
    ]
    workspace, report, _ = run_audit(bib, methods=providers, client=FakeClient())
    original = workspace.final.read_bytes()
    p = providers[0]
    if change == "revision":
        p.descriptor = replace(p.descriptor, adapter_version="2")
    elif change == "policy":
        p.descriptor = replace(
            p.descriptor, request_policy=replace(p.descriptor.request_policy, max_pages=4)
        )
    elif change == "configuration":
        p.descriptor = replace(p.descriptor, discovery_config=(("venue", "configured"),))
    else:
        providers.reverse()
    _, partial, _ = run_audit(bib, citation_key="Example", methods=providers, client=FakeClient())
    assert workspace.final.read_bytes() == original
    assert "correctness" not in partial["items"][1]["validations"]
    assert not partial["verification_run"]["complete"] and workspace.checkpoint.exists()


def test_legacy_methods_are_not_borrowed(bib):
    p = FixtureProvider(payload=PAYLOAD)
    workspace, report, _ = run_audit(bib, methods=[p], client=FakeClient())
    report["verification_run"] = {
        "fingerprint": report["verification_run"]["fingerprint"],
        "methods": ["crossref", "openalex", "publisher"],
        "policy_version": 4,
        "orchestration_version": 1,
    }
    report["items"][0]["validations"]["correctness"]["methods"][0]["name"] = "publisher"
    workspace.final.write_text(json.dumps(report))
    legacy = copy.deepcopy(report)
    _, current, _ = run_audit(bib, methods=[p], client=FakeClient())
    assert [m["name"] for m in current["items"][0]["validations"]["correctness"]["methods"]] == [
        "fixture"
    ]
    validate_report(legacy)
    assert legacy["items"][0]["validations"]["correctness"]["methods"][0]["name"] == "publisher"


def test_partial_discovery_and_independent_success():
    record = Candidate.from_record(
        {
            **{
                "title": "An Example Paper",
                "authors": [{"given": "Jane", "family": "Smith"}],
                "year": "2024",
                "venue": "Example Journal",
                "identifiers": {"doi": "10.1234/example"},
            },
            "url": "https://fixture.test/paper",
            "record_type": "publication",
            "publication_status": "published",
        },
        provenance={"source": "catalog"},
    )

    def partial(*_):
        return LookupResult(
            (record,),
            (LookupAttempt("catalog", "year 2024", complete=False),),
            False,
            "Page budget exhausted",
        )

    p = FixtureProvider("partial", lookup=partial)
    decision = verify_reference(ENTRY, FakeClient(), methods=[p])
    assert decision["is_correct"] is None and not decision["methods"][0]["differences"]
    assert (
        decision["methods"][0]["candidates"]
        and decision["methods"][0]["error"]["code"] == "incomplete_search"
    )
    decision = verify_reference(ENTRY, FakeClient(), methods=[p, FixtureProvider(payload=PAYLOAD)])
    assert decision["is_correct"] is True and decision["consensus"]["unavailable"] == 1
    assert decision["consensus"]["display"] == "1/1"


def test_identifier_only_keeps_retrieved_candidate_without_verdict():
    entry = copy.deepcopy(ENTRY)
    del entry["fields"]["title"]
    result = verify_reference(entry, FakeClient(), methods=[FixtureProvider(payload=PAYLOAD)])
    assert result["is_correct"] is None
    assert result["methods"][0]["rejected_candidates"][0]["title"] == "An Example Paper"


def test_unqualified_review_record_cannot_confirm_publication():
    def retrieve(*_):
        record = Candidate.from_record(
            {
                "title": PAYLOAD["heading"],
                "authors": PAYLOAD["people"],
                "year": PAYLOAD["date"],
                "venue": PAYLOAD["journal"],
                "identifiers": PAYLOAD["ids"],
                "url": "https://fixture.test/paper",
                "record_type": "unknown",
                "publication_status": "submitted",
            },
            provenance={"source": "submission"},
        )
        return LookupResult((record,), (LookupAttempt("note", "forum"),))

    p = FixtureProvider(lookup=retrieve)
    p.descriptor = replace(p.descriptor, evidence_category="review_platform")
    result = verify_reference(ENTRY, FakeClient(), methods=[p])
    assert result["methods"][0]["status"] == "found" and not result["methods"][0]["authority"]
    assert result["is_correct"] is None


def test_priorities_do_not_hide_primary_conflicts():
    a = FixtureProvider("a", payload=PAYLOAD)
    b = FixtureProvider("b", payload={**PAYLOAD, "date": "2024"})
    b.descriptor = replace(b.descriptor, canonical_priority=-10)
    result = verify_reference(ENTRY, FakeClient(), methods=[a, b])
    assert result["canonical_ref"]["year"] == "2024" and result["is_correct"] is None
    assert "conflict" in result["reason"]


def test_default_sources_no_retired_network_requests(tmp_path):
    fixtures = Path(__file__).parent / "fixtures/providers"
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.host == "export.arxiv.org":
            body = (fixtures / "arxiv.xml").read_text()
        elif request.url.host == "api2.openreview.net":
            body = (fixtures / "openreview-v2.json").read_text()
        else:
            body = "<html>No catalogs</html>"
        return httpx.Response(200, text=body)

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    result = verify_reference(ENTRY, client)
    assert [m["name"] for m in result["methods"]] == list(METHODS)
    allowed = {h for p in METHODS.values() for h in p.descriptor.allowed_hosts}
    assert all(request.url.host in allowed for request in calls)
    assert result["policy_version"] == 8
    client.close()


def test_inapplicable_and_malformed_contract_are_isolated():
    p = FixtureProvider()
    p.applicability = lambda q: Applicability("inapplicable", "Unsupported entry")
    result = verify_reference(ENTRY, FakeClient(), methods=[p])
    assert (
        result["methods"][0]["status"] == "not_applicable"
        and result["consensus"]["applicable"] == 0
    )
    p.applicability = lambda q: "applicable"
    result = verify_reference(
        ENTRY, FakeClient(), methods=[p, FixtureProvider("valid", payload=PAYLOAD)]
    )
    assert (
        result["methods"][0]["error"]["code"] == "invalid_response" and result["is_correct"] is True
    )


@pytest.mark.parametrize(
    "mutation", ["provider", "protocol", "version", "priority", "provenance", "complete"]
)
def test_malformed_additive_metadata_rejected_without_writes(bib, mutation):
    workspace, report, _ = run_audit(
        bib, methods=[FixtureProvider(payload=PAYLOAD)], client=FakeClient()
    )
    outcome = report["items"][0]["validations"]["correctness"]["methods"][0]
    if mutation == "provider":
        report["verification_run"]["providers"][0]["adapter_version"] = []
    elif mutation == "protocol":
        report["verification_run"]["provider_protocol_version"] = True
    elif mutation == "version":
        outcome["adapter_version"] = []
    elif mutation == "priority":
        outcome["canonical_priority"] = "first"
    elif mutation == "provenance":
        outcome["lookup_provenance"] = [None]
    else:
        outcome["lookup_complete"] = "yes"
    workspace.checkpoint.write_text(json.dumps(report))
    before = workspace.final.read_bytes()
    checkpoint = workspace.checkpoint.read_bytes()
    with pytest.raises(ValueError):
        run_audit(bib, methods=[FixtureProvider()], client=FakeClient())
    assert (
        workspace.final.read_bytes() == before and workspace.checkpoint.read_bytes() == checkpoint
    )


def test_cache_reused_after_revision_change_without_rewriting_raw(tmp_path):
    bib = tmp_path / "arxiv.bib"
    bib.write_text(
        "@article{A,title={An Example Paper},author={Jane Smith},year={2025},"
        "journal={arXiv},eprint={2501.12345v1}}"
    )
    p = copy.copy(METHODS["arxiv"])
    calls = []
    body = (Path(__file__).parent / "fixtures/providers/arxiv.xml").read_text()
    client = MetadataClient(
        tmp_path / "audit/cache",
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, text=body)),
    )
    workspace, _, _ = run_audit(bib, output=tmp_path / "audit", methods=[p], client=client)
    raw = {
        str(f.relative_to(workspace.cache)): f.read_bytes()
        for f in workspace.cache.rglob("*")
        if f.is_file() and f.suffix != ".lock"
    }
    p.descriptor = replace(p.descriptor, adapter_version="2")
    _, report, _ = run_audit(bib, output=workspace.root, methods=[p], client=client)
    assert (
        len(calls) == 1
        and report["items"][0]["validations"]["correctness"]["methods"][0]["requests"][-1]["cached"]
    )
    assert all((workspace.cache / f).read_bytes() == body for f, body in raw.items())
    client.close()


def test_shared_selection_keeps_rejected_candidates_after_success():
    p = FixtureProvider(payload=PAYLOAD)
    good = p.lookup(None, None).candidates[0]
    bad = replace(good, title="Completely Unrelated Research")
    p.retrieval = lambda *_: LookupResult(
        (bad, good), (LookupAttempt("direct", "wrong id"), LookupAttempt("title", "catalog"))
    )
    result = verify_reference(ENTRY, FakeClient(), methods=[p])
    source = result["methods"][0]
    assert source["found_ref"]["title"] == "An Example Paper" and result["is_correct"] is True
    assert source["rejected_candidates"][0]["title"] == "Completely Unrelated Research"
    assert source["matched_candidates"][0] == source["found_ref"]
    assert len(source["lookup_provenance"]) == 2
