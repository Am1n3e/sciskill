import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from provider_support import assert_contract
from support import ENTRY

from bib_lint.audit import run_audit
from bib_lint.verification import verify_reference
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.common import citation_candidate
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery

FIXTURES = Path(__file__).parent / "fixtures" / "providers"
DIRECT = {
    "arxiv": "https://arxiv.org/abs/2501.12345v1",
    "pmlr": "https://proceedings.mlr.press/v267/example25a.html",
    "jmlr": "https://jmlr.org/papers/v26/25-001.html",
    "acl_anthology": "https://aclanthology.org/2025.acl-long.1/",
    "neurips": "https://proceedings.neurips.cc/paper_files/paper/2025/hash/abc-Abstract-Conference.html",
    "openreview": "https://openreview.net/forum?id=Paper123",
}
EMPTY_FEED = '<feed xmlns="http://www.w3.org/2005/Atom"/>'


def payload(name):
    return (
        FIXTURES
        / (
            "arxiv.xml"
            if name == "arxiv"
            else "openreview-v2.json"
            if name == "openreview"
            else "publication.html"
        )
    ).read_text()


def query(name, *, direct=True):
    entry = copy.deepcopy(ENTRY)
    if direct:
        entry["fields"]["url"] = DIRECT[name]
    elif name == "pmlr":
        entry["fields"]["journal"] = "International Conference on Machine Learning"
    elif name == "acl_anthology":
        entry["fields"]["journal"] = "ACL"
    return LookupQuery.from_entry(entry)


def client_for(tmp_path, provider, handler):
    calls = []

    def respond(request):
        calls.append(request)
        return handler(request)

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    return client, RequestContext(client, provider.descriptor, "Example"), calls


@pytest.mark.parametrize("name", list(METHODS))
def test_direct_contract_and_normalization(tmp_path, name):
    provider = METHODS[name]
    client, context, calls = client_for(
        tmp_path, provider, lambda _: httpx.Response(200, text=payload(name))
    )
    result = assert_contract(provider, query(name), context)
    assert result.complete and len(result.candidates) == 1
    record = result.candidates[0].as_record()
    assert record["title"] == "An Example Paper"
    assert record["authors"][0]["family"] == "Smith"
    assert record["year"] == "2025"
    assert record["provenance"] and len(calls) == 1
    assert all(r.url.host in provider.descriptor.allowed_hosts for r in calls)
    client.close()


def discovery_response(name, request):
    url = str(request.url)
    if name in {"arxiv", "openreview"}:
        return httpx.Response(200, text=payload(name))
    if url.rstrip("/") == DIRECT[name].rstrip("/"):
        return httpx.Response(200, text=payload(name))
    if name == "pmlr":
        body = (
            '<li><a href="v267">Volume 267</a> Proceedings of ICML 2025</li>'
            if request.url.path == "/"
            else f'<a href="{DIRECT[name]}">An Example Paper</a>'
        )
    elif name == "jmlr":
        body = (
            '<li><a href="v26">Volume 26</a> January 2025</li>'
            if request.url.path == "/papers/"
            else f'<a href="{DIRECT[name]}">An Example Paper</a>'
        )
    elif name == "acl_anthology":
        if request.url.path.startswith("/events/acl-2025"):
            body = '<a href="/volumes/2025.acl-long/">ACL 2025</a>'
        elif request.url.path.startswith("/events/"):
            body = "<html>No volumes</html>"
        else:
            body = f'<a href="{DIRECT[name]}">An Example Paper</a>'
    else:
        body = (
            '<a href="/paper_files/paper/2025">2025</a>'
            if request.url.path == "/"
            else f'<a href="{DIRECT[name]}">An Example Paper</a>'
        )
    return httpx.Response(200, text=body)


@pytest.mark.parametrize("name", list(METHODS))
def test_title_discovery_without_url(tmp_path, name):
    provider = METHODS[name]
    client, context, calls = client_for(tmp_path, provider, lambda r: discovery_response(name, r))
    result = assert_contract(provider, query(name, direct=False), context)
    assert result.candidates and result.complete
    assert any(a.strategy in {"title", "catalog"} for a in result.attempts)
    assert all(r.url.host in provider.descriptor.allowed_hosts for r in calls)
    client.close()


@pytest.fixture
def pmlr_catalog(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@inproceedings{thomas2015hcpi,title={High Confidence Policy Improvement},"
        "author={Thomas, Philip and Theocharous, Georgios and Ghavamzadeh, Mohammad},"
        "year={2015},booktitle={ICML}}"
    )
    output = tmp_path / "audit"
    calls = []
    responses = {
        "/": '<li><a href="v37">Volume 37</a> Proceedings of ICML 2015</li>',
        "/v37/": (FIXTURES / "pmlr-volume.html").read_text(),
        "/v37/thomas15.html": (FIXTURES / "pmlr-paper.html").read_text(),
    }

    def respond(request):
        calls.append(request.url.path)
        assert request.url.path in responses, "Unrelated paper or PDF requested"
        return httpx.Response(200, text=responses[request.url.path])

    client = MetadataClient(output / "cache", transport=httpx.MockTransport(respond))
    yield bib, output, client, calls
    client.close()


def test_pmlr_discovers_paper_from_real_volume_layout(pmlr_catalog):
    bib, output, client, calls = pmlr_catalog
    _, report, _ = run_audit(bib, output=output, client=client, methods=[METHODS["pmlr"]])
    source = report["items"][0]["validations"]["correctness"]["methods"][0]
    assert source["status"] == "found"
    assert source["found_ref"]["title"] == "High Confidence Policy Improvement"
    assert source["source_url"] == "https://proceedings.mlr.press/v37/thomas15.html"
    assert calls == ["/", "/v37/", "/v37/thomas15.html"]


def test_pmlr_rechecks_saved_v2_miss_with_cached_catalog(pmlr_catalog):
    bib, output, client, calls = pmlr_catalog
    legacy = copy.copy(METHODS["pmlr"])
    legacy.descriptor = replace(legacy.descriptor, adapter_version="2")
    legacy.paper_links = lambda *_: iter(())
    workspace, report, _ = run_audit(bib, output=output, client=client, methods=[legacy])
    assert report["items"][0]["validations"]["correctness"]["methods"][0]["status"] == "not_found"
    raw = {
        path: path.read_bytes()
        for path in workspace.cache.rglob("*")
        if path.is_file() and path.name != "checksum.json" and path.suffix != ".lock"
    }
    _, report, _ = run_audit(bib, output=output, client=client, methods=[METHODS["pmlr"]])
    source = report["items"][0]["validations"]["correctness"]["methods"][0]
    assert source["status"] == "found"
    assert calls == ["/", "/v37/", "/v37/thomas15.html"]
    assert [request["cached"] for request in source["requests"]] == [True, True, False]
    assert all(path.read_bytes() == body for path, body in raw.items())


@pytest.mark.parametrize("name", list(METHODS))
def test_empty_scoped_search(tmp_path, name):
    body = (
        EMPTY_FEED
        if name == "arxiv"
        else '{"notes":[],"count":0}'
        if name == "openreview"
        else "<html><body>No papers</body></html>"
    )
    provider = METHODS[name]
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, text=body))
    result = assert_contract(provider, query(name), context)
    assert result.complete and not result.candidates and result.attempts
    client.close()


@pytest.mark.parametrize("name", list(METHODS))
def test_malformed_saved_as_independent_failure(tmp_path, name):
    provider = METHODS[name]
    client, _, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, text="malformed"))
    entry = copy.deepcopy(ENTRY)
    entry["fields"]["url"] = DIRECT[name]
    decision = verify_reference(entry, client, methods=[provider])
    assert decision["is_correct"] is None
    assert decision["methods"][0]["status"] == "error"
    assert decision["methods"][0]["error"]["code"] == "invalid_response"
    client.close()


@pytest.mark.parametrize("name", list(METHODS))
def test_rate_limits_are_source_failures(tmp_path, name):
    provider = METHODS[name]
    client, _, calls = client_for(
        tmp_path, provider, lambda _: httpx.Response(429, headers={"Retry-After": "100"})
    )
    entry = copy.deepcopy(ENTRY)
    entry["fields"]["url"] = DIRECT[name]
    decision = verify_reference(entry, client, methods=[provider])
    assert decision["methods"][0]["error"]["code"] == "rate_limited"
    assert decision["is_correct"] is None and len(calls) == 1
    client.close()


@pytest.mark.parametrize("name", ["pmlr", "jmlr", "acl_anthology", "neurips"])
def test_archive_needs_context_and_keeps_missing_fields(tmp_path, name):
    provider = METHODS[name]
    q = replace(query(name, direct=False), year=None)
    assert provider.applicability(q).state == "insufficient_context"
    text = '<meta name="citation_title" content="An Example Paper">'
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, text=text))
    result = assert_contract(provider, query(name), context)
    assert result.candidates[0].year is None and not result.candidates[0].authors
    client.close()


@pytest.mark.parametrize("name", ["pmlr", "jmlr", "acl_anthology", "neurips"])
def test_archive_catalog_budget_keeps_partial_evidence(tmp_path, name):
    provider = copy.copy(METHODS[name])
    provider.descriptor = replace(
        provider.descriptor,
        request_policy=replace(provider.descriptor.request_policy, max_fetches=2),
    )
    client, context, _ = client_for(tmp_path, provider, lambda r: discovery_response(name, r))
    result = assert_contract(provider, query(name, direct=False), context)
    assert not result.complete and "budget" in result.diagnostic
    client.close()


def test_arxiv_unrelated_id_fallback_and_version_provenance(tmp_path):
    provider = METHODS["arxiv"]
    feed = payload("arxiv")

    def respond(request):
        return httpx.Response(
            200,
            text=feed.replace("An Example Paper", "Completely Unrelated Research")
            if "id_list" in request.url.params
            else feed,
        )

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("arxiv"), context)
    assert len(calls) == 2 and len(result.candidates) == 2
    assert [a.strategy for a in result.attempts] == ["arxiv_id", "title"]
    assert result.candidates[-1].version == "2501.12345v1"
    client.close()


def test_arxiv_pagination_budget_preserves_candidates(tmp_path):
    provider = copy.copy(METHODS["arxiv"])
    provider.descriptor = replace(
        provider.descriptor, request_policy=replace(provider.descriptor.request_policy, max_pages=1)
    )
    feed = payload("arxiv").replace(">1</opensearch:totalResults>", ">50</opensearch:totalResults>")
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, text=feed))
    result = assert_contract(provider, query("arxiv", direct=False), context)
    assert not result.complete and result.candidates
    client.close()


@pytest.mark.parametrize("name", ["pmlr", "jmlr", "acl_anthology", "neurips"])
def test_archive_identifier_direct(name):
    q = query(name, direct=False)
    key, identifier = {
        "pmlr": ("pmlr", "v267/example25a"),
        "jmlr": ("jmlr", "v26/25-001"),
        "acl_anthology": ("acl", "2025.acl-long.1"),
        "neurips": ("neurips", "paper_files/paper/2025/hash/abc-Abstract-Conference.html"),
    }[name]
    q = replace(q, fields=q.fields + ((key, identifier),))
    assert METHODS[name].direct_url(q) == DIRECT[name]


@pytest.mark.parametrize("identifier", ["P19-1001", "2025.acl-long.1", "2020.emnlp-main.23"])
def test_acl_identifier_formats(identifier):
    q = replace(query("acl_anthology", direct=False), fields=(("acl", identifier),))
    assert METHODS["acl_anthology"].direct_url(q) == f"https://aclanthology.org/{identifier}/"


def test_acl_source_bibtex_fallback(tmp_path):
    provider = METHODS["acl_anthology"]

    def respond(request):
        return httpx.Response(
            200,
            text=(
                "@inproceedings{paper,title={An Example Paper},author={Smith, Jane},"
                "year={2025},booktitle={ACL}}"
            )
            if request.url.path.endswith(".bib")
            else '<a href="/2025.acl-long.1.bib">BibTeX</a>',
        )

    client, context, _ = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("acl_anthology"), context)
    assert result.candidates[0].venue == "ACL"
    assert result.candidates[0].provenance and result.candidates[0].year == "2025"
    client.close()


@pytest.mark.parametrize("series", ["ICLR.cc", "ICML.cc", "NeurIPS.cc", "TMLR"])
def test_openreview_accepted_venue_series(tmp_path, series):
    data = json.loads(payload("openreview"))
    data["notes"][0]["content"]["venueid"]["value"] = (
        series if series == "TMLR" else series + "/2025/Conference"
    )
    data["notes"][0]["content"]["year"] = {"value": "2025"}
    provider = METHODS["openreview"]
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, json=data))
    record = assert_contract(provider, query("openreview"), context).candidates[0]
    assert record.publication_status == "accepted" and record.record_type == "publication"
    client.close()


@pytest.mark.parametrize(
    "suffix,status",
    [
        ("Submission", "submitted"),
        ("Rejected_Submission", "rejected"),
        ("Withdrawn_Submission", "withdrawn"),
        ("Workshop", "unknown"),
    ],
)
def test_openreview_unpublished_anonymous_timestamps(tmp_path, suffix, status):
    data = json.loads(payload("openreview"))
    note = data["notes"][0]
    note["content"]["venueid"]["value"] = "ICLR.cc/2025/Conference/" + suffix
    note["content"]["authors"]["value"] = ["Anonymous"]
    note["cdate"] = note["mdate"] = note["pdate"] = 1735689600000
    provider = METHODS["openreview"]
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, json=data))
    record = assert_contract(provider, query("openreview"), context).candidates[0]
    assert record.publication_status == status and record.record_type == "unknown"
    assert record.year is None and record.venue is None and not record.authors
    assert dict(record.provenance)["pdate"] == "1735689600000"
    client.close()


def test_openreview_api1_decision_and_reply_exclusion(tmp_path):
    provider = METHODS["openreview"]
    data = json.loads((FIXTURES / "openreview-v1.json").read_text())
    data["notes"].append({"id": "Reply", "forum": "Paper123", "replyto": "Paper123", "content": {}})

    def respond(request):
        return httpx.Response(
            200, json={"notes": []} if request.url.host == "api2.openreview.net" else data
        )

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("openreview"), context)
    record = result.candidates[0]
    assert record.publication_status == "accepted" and record.year == "2023"
    assert record.authors[0].given == "Jane" and len(result.candidates) == 1
    assert len(calls) == 2
    client.close()


def test_no_query_hint_is_normalized_as_source_fact():
    record = citation_candidate(
        '<meta name="citation_title" content="Title">', "https://fixture.test/paper"
    )
    assert record.year is None and record.venue is None and not record.authors


def test_openreview_venue_discovery_after_empty_title_search(tmp_path):
    provider = METHODS["openreview"]

    def respond(request):
        return httpx.Response(
            200,
            text=payload("openreview")
            if request.url.path == "/notes"
            else '{"notes":[],"count":0}',
        )

    client, context, calls = client_for(tmp_path, provider, respond)
    q = replace(query("openreview", direct=False), venue="ICLR")
    result = assert_contract(provider, q, context)
    assert result.candidates and result.attempts[-1].strategy == "venue"
    assert calls[-1].url.params["content.venueid"] == "ICLR.cc/2025/Conference"
    client.close()


def test_pmlr_adjacent_year_does_not_copy_hint(tmp_path):
    provider = METHODS["pmlr"]

    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200, text='<li><a href="v267">Volume 267</a> Proceedings of ICML 2025</li>'
            )
        return discovery_response("pmlr", request)

    client, context, _ = client_for(tmp_path, provider, respond)
    q = replace(query("pmlr", direct=False), year="2024")
    result = assert_contract(provider, q, context)
    assert result.candidates[0].year == "2025"
    assert result.attempts[-1].scope.endswith("/v267/")
    client.close()


def test_jmlr_old_identifier_and_allowed_redirect(tmp_path):
    provider = METHODS["jmlr"]
    q = replace(query("jmlr", direct=False), fields=(("jmlr", "volume2/example"),))
    assert provider.direct_url(q) == "https://jmlr.org/papers/volume2/example.html"

    def respond(request):
        if request.url.host == "www.jmlr.org":
            return httpx.Response(302, headers={"Location": DIRECT["jmlr"]})
        return httpx.Response(200, text=payload("jmlr"))

    client, context, _ = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, replace(q, input_url="http://www.jmlr.org/start"), context)
    assert result.candidates
    client.close()


def test_acl_generic_year_catalog_routes_real_events(tmp_path):
    provider = METHODS["acl_anthology"]

    def respond(request):
        if request.url.path == "/events/":
            return httpx.Response(200, text='<a href="/events/acl-2025/">ACL 2025</a>')
        return discovery_response("acl_anthology", request)

    client, context, _ = client_for(tmp_path, provider, respond)
    result = assert_contract(
        provider, replace(query("acl_anthology", direct=False), venue=None), context
    )
    assert result.candidates and result.complete
    client.close()


def test_neurips_old_host_direct(tmp_path):
    provider = METHODS["neurips"]
    client, context, _ = client_for(
        tmp_path, provider, lambda _: httpx.Response(200, text=payload("neurips"))
    )
    result = assert_contract(
        provider,
        replace(
            query("neurips"), input_url="https://papers.nips.cc/paper/2020/hash/abc-Abstract.html"
        ),
        context,
    )
    assert result.candidates[0].url.startswith("https://papers.nips.cc/")
    client.close()


def test_jmlr_real_definition_list_catalog_layout():
    provider = METHODS["jmlr"]
    text = (
        "<dl><dt>An Example Paper</dt><dd><b>Jane Smith</b>; 2025 "
        '[<a href="/papers/v26/25-001.html">abs</a>]</dd></dl>'
    )
    assert list(
        provider.paper_links(text, "https://jmlr.org/papers/v26/", query("jmlr", direct=False))
    ) == [DIRECT["jmlr"]]


@pytest.mark.parametrize("name", list(METHODS))
def test_each_provider_identifier_only_and_nonapplicability(tmp_path, name):
    provider = METHODS[name]
    assert (
        provider.applicability(
            replace(query(name, direct=False), title=None, year=None, identifiers=(), fields=())
        ).state
        == "inapplicable"
    )
    q = replace(query(name), title=None)
    client, context, _ = client_for(
        tmp_path, provider, lambda _: httpx.Response(200, text=payload(name))
    )
    result = assert_contract(provider, q, context)
    assert result.candidates and result.complete
    client.close()


@pytest.mark.parametrize("name", list(METHODS))
@pytest.mark.parametrize("mutation", ["credentials", "port", "scheme"])
def test_supported_input_urls_reject_nonstandard_forms(tmp_path, name, mutation):
    from urllib.parse import urlsplit

    url = DIRECT[name]
    parsed = urlsplit(url)
    if mutation == "credentials":
        url = parsed._replace(netloc="user:password@" + parsed.netloc).geturl()
    elif mutation == "port":
        url = parsed._replace(netloc=parsed.netloc + ":999").geturl()
    else:
        url = parsed._replace(scheme="ftp").geturl()
    entry = copy.deepcopy(ENTRY)
    entry["fields"]["url"] = url
    provider = METHODS[name]
    client, _, calls = client_for(
        tmp_path, provider, lambda _: pytest.fail("Nonstandard URL fetched")
    )
    decision = verify_reference(entry, client, methods=[provider])
    assert not calls and decision["methods"][0]["error"]["code"] == "unsupported_url"
    client.close()


@pytest.mark.parametrize("name", ["pmlr", "jmlr", "acl_anthology", "neurips"])
def test_archive_direct_404_falls_back_to_catalog(tmp_path, name):
    provider = METHODS[name]
    bad = (
        DIRECT[name]
        .replace("example25a", "missing")
        .replace("25-001", "missing")
        .replace(".1/", ".9999/")
        .replace("abc-Abstract", "missing-Abstract")
    )

    def respond(request):
        return httpx.Response(404) if str(request.url) == bad else discovery_response(name, request)

    client, context, _ = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, replace(query(name, direct=False), input_url=bad), context)
    assert result.candidates and result.complete
    assert result.attempts[0].diagnostic.startswith("HTTP 404")
    client.close()


def test_archive_direct_miss_without_title_or_routing_context(tmp_path):
    provider = METHODS["pmlr"]
    client, context, _ = client_for(
        tmp_path, provider, lambda _: httpx.Response(200, text="<html>No metadata</html>")
    )
    result = assert_contract(provider, replace(query("pmlr"), title=None), context)
    assert not result.candidates and result.complete
    client.close()
    client, context, _ = client_for(
        tmp_path / "missing",
        provider,
        lambda _: httpx.Response(200, text="<html>No metadata</html>"),
    )
    result = assert_contract(provider, replace(query("pmlr"), year=None), context)
    assert not result.complete and "routing context" in result.diagnostic
    client.close()


def test_arxiv_doi_and_error_record():
    provider = METHODS["arxiv"]
    from defusedxml import ElementTree

    xml = payload("arxiv").replace(
        "<entry>", '<entry xmlns:x="http://arxiv.org/schemas/atom"><x:doi>10.1234/PUBLISHED</x:doi>'
    )
    entries = ElementTree.fromstring(xml).findall("{http://www.w3.org/2005/Atom}entry")
    record = next(provider._records(entries))
    assert (
        dict(record.identifiers)["doi"] == "10.1234/published" and record.record_type == "preprint"
    )
    xml = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>error</id></entry></feed>'
    with pytest.raises(LookupFailure, match="error record"):
        list(
            provider._records(
                ElementTree.fromstring(xml).findall("{http://www.w3.org/2005/Atom}entry")
            )
        )


def test_arxiv_custom_identifier_without_title():
    q = replace(
        query("arxiv", direct=False),
        title=None,
        identifiers=(),
        fields=(("arxiv_id", "2501.12345v2"),),
    )
    assert METHODS["arxiv"].identifier(q) == "2501.12345v2"
    assert METHODS["arxiv"].applicability(q).state == "applicable"


@pytest.mark.parametrize(
    "data",
    [
        {"notes": [None]},
        {"notes": [{"id": "Paper", "content": []}]},
        {"notes": [{"content": {"title": "Title"}}]},
        {"notes": [{"id": "Paper", "content": {"title": "Title", "authors": "Anonymous"}}]},
        {"notes": None},
        [],
    ],
)
def test_openreview_malformed_structured_payloads(tmp_path, data):
    provider = METHODS["openreview"]
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, json=data))
    with pytest.raises(LookupFailure):
        assert_contract(provider, query("openreview"), context)
    assert context.lookup_attempts[-1].complete is False
    client.close()


def test_openreview_title_fallback_to_api1_and_custom_id(tmp_path):
    provider = METHODS["openreview"]
    q = replace(
        query("openreview", direct=False), fields=(("openreview_id", "Paper123"),), title=None
    )
    assert provider.identifier(q) == "Paper123"

    def respond(request):
        return (
            httpx.Response(403)
            if request.url.host == "api2.openreview.net"
            else httpx.Response(200, text=payload("openreview"))
        )

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("openreview", direct=False), context)
    assert result.candidates and calls[-1].url.host == "api.openreview.net"
    client.close()


def test_openreview_budget_retains_partial_notes(tmp_path):
    provider = copy.copy(METHODS["openreview"])
    provider.descriptor = replace(
        provider.descriptor, request_policy=replace(provider.descriptor.request_policy, max_pages=1)
    )
    data = json.loads(payload("openreview"))
    data["count"] = 100
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, json=data))
    result = assert_contract(provider, query("openreview", direct=False), context)
    assert not result.complete and result.candidates and "budget" in result.diagnostic
    client.close()


def test_openreview_decision_scope_and_rejected_older_note():
    provider = METHODS["openreview"]
    data = json.loads((FIXTURES / "openreview-v1.json").read_text())
    note = data["notes"][0]
    reply = note["details"]["directReplies"][0]
    reply["invitation"] = "ICLR.cc/2022/Conference/Paper1/-/Decision"
    record = next(provider._records([note]))
    assert record.publication_status == "submitted"
    reply["invitation"] = "ICLR.cc/2023/Conference/Paper1/-/Decision"
    reply["content"]["decision"] = "Reject"
    record = next(provider._records([note]))
    assert record.publication_status == "rejected"
    reply["forum"] = "OtherPaper"
    reply["content"]["decision"] = "Accept (Poster)"
    assert next(provider._records([note])).publication_status == "submitted"
    reply["forum"] = "Paper123"
    reply["invitation"] = "Other.cc/2023/Conference/-/Decision"
    assert next(provider._records([note])).publication_status == "submitted"


def test_openreview_reply_invitations_and_unknown_venue():
    provider = METHODS["openreview"]
    note = json.loads(payload("openreview"))["notes"][0]
    note["invitations"] = ["ICLR.cc/2025/Conference/Paper1/-/Review"]
    assert not list(provider._records([note]))
    note.pop("invitations")
    note["content"]["venueid"]["value"] = "TMLRimpersonation"
    assert next(provider._records([note])).record_type == "unknown"


@pytest.mark.parametrize(
    "name,volume", [("pmlr", "267"), ("jmlr", "26"), ("acl_anthology", "2025.acl-long")]
)
def test_archive_volume_discovery_without_year(tmp_path, name, volume):
    provider = METHODS[name]
    q = replace(query(name, direct=False), year=None, fields=(("volume", volume),))
    client, context, calls = client_for(tmp_path, provider, lambda r: discovery_response(name, r))
    result = assert_contract(provider, q, context)
    assert result.candidates and result.complete and result.candidates[0].year == "2025"
    assert len(calls) == 2
    assert result.attempts[0].scope == provider.volume_catalog(q)
    client.close()


def test_openreview_public_author_objects(tmp_path):
    data = json.loads(payload("openreview"))
    data["notes"][0]["content"]["authors"]["value"] = [
        {"fullname": "Jane Smith", "username": "~Jane_Smith1"},
        "John Doe",
    ]
    provider = METHODS["openreview"]
    client, context, _ = client_for(tmp_path, provider, lambda _: httpx.Response(200, json=data))
    record = assert_contract(provider, query("openreview"), context).candidates[0]
    assert [author.family for author in record.authors] == ["Smith", "Doe"]
    client.close()


@pytest.mark.parametrize("name", ["pmlr", "acl_anthology"])
def test_broad_archive_discovery_requests_routing_context(tmp_path, name):
    provider = METHODS[name]
    if name == "pmlr":
        body = "".join(f'<li><a href="v{i}">Volume {i}</a> Conference 2025</li>' for i in range(20))
    else:
        body = "".join(f'<a href="/events/event{i}-2025/">Event</a>' for i in range(20))
    client, context, calls = client_for(
        tmp_path, provider, lambda _: httpx.Response(200, text=body)
    )
    result = assert_contract(provider, replace(query(name, direct=False), venue=None), context)
    assert not result.complete
    assert "provide a venue, volume, or direct paper URL" in result.diagnostic
    assert len(calls) == 1  # No crawl through unrelated event or volume pages.
    client.close()


def test_archive_stops_after_matching_catalog(tmp_path):
    provider = METHODS["pmlr"]

    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                text="".join(
                    f'<li><a href="v{i}">Volume {i}</a> ICML 2025</li>' for i in range(20)
                ),
            )
        return discovery_response("pmlr", request)

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("pmlr", direct=False), context)
    assert result.complete and result.candidates
    assert len(calls) == 3
    client.close()


def test_openreview_title_search_uses_phrase_not_any_word(tmp_path):
    provider = METHODS["openreview"]

    def respond(request):
        assert request.url.params["type"] == "exact"
        assert request.url.params["content"] == "title"
        assert request.url.params["term"] == "an example paper"
        return httpx.Response(200, json=json.loads(payload("openreview")))

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("openreview", direct=False), context)
    assert result.complete and result.candidates and len(calls) == 1
    client.close()


def test_neurips_official_datasets_catalog_host(tmp_path):
    provider = METHODS["neurips"]
    host = "datasets-benchmarks-proceedings.neurips.cc"

    def respond(request):
        if request.url.host == "proceedings.neurips.cc":
            body = f'<a href="https://{host}/paper/2025">Datasets and Benchmarks 2025</a>'
        elif request.url.path == "/paper/2025":
            body = '<a href="/paper/2025/hash/abc-Abstract.html">An Example Paper</a>'
        else:
            body = payload("neurips")
        return httpx.Response(200, text=body)

    client, context, calls = client_for(tmp_path, provider, respond)
    result = assert_contract(provider, query("neurips", direct=False), context)
    assert result.complete and result.candidates
    assert calls[-1].url.host == host
    client.close()
