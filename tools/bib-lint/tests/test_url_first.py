"""Locator-first acceptance contracts, exercised through production components."""

import json
import signal
import threading
from collections import Counter
from dataclasses import asdict
from queue import SimpleQueue

import httpx
import pytest

from bib_lint.audit import run_audit
from bib_lint.storage import ReportLockError
from bib_lint.verification import _consensus_with_input, _source_result
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery
from bib_lint.verification.queues import ProviderQueues
from bib_lint.verification.routing import plan_lookups, resolved
from bib_lint.verification.workflow import ProviderLookup


def entry(url="https://proceedings.mlr.press/v235/example24a.html", **fields):
    return {
        "key": "example",
        "fields": {"title": "An Example Paper", "year": "2024", "url": url, **fields},
        "persons": {"author": [{"first": ["Jane"], "last": ["Smith"]}]},
    }


def metadata(title="An Example Paper", year="2024"):
    return (
        f'<meta name="citation_title" content="{title}">'
        '<meta name="citation_author" content="Jane Smith">'
        f'<meta name="citation_publication_date" content="{year}">'
    )


def lookup(item, provider, client):
    query = LookupQuery.from_entry(item)
    step = plan_lookups(item, METHODS)[0]
    context = RequestContext(client, provider.descriptor, query.citation_key)
    return _source_result(
        provider, query, context, retrieval=step.query(query), strategy=step.strategy
    )


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://arxiv.org/abs/2401.12345", "arxiv"),
        ("https://arxiv.org/pdf/2401.12345.pdf", "arxiv"),
        ("https://proceedings.mlr.press/v235/example24a.html", "pmlr"),
        ("https://jmlr.org/papers/v25/24-001.html", "jmlr"),
        ("https://aclanthology.org/2024.acl-long.1/", "acl_anthology"),
        ("https://proceedings.neurips.cc/paper/2024/hash/abc-Abstract.html", "neurips"),
        ("https://openreview.net/forum?id=Example", "openreview"),
        ("https://arxiv.org.evil.test/abs/2401.12345", None),
        ("https://arxiv.org@evil.test/abs/2401.12345", None),
        ("https://arxiv.org:8443/abs/2401.12345", None),
        ("https://arxiv.org/abs/2401.12345\n", None),
        ("https://arxiv.org/search", None),
        ("https://openreview.net/forum?id=one&id=two", None),
        ("https://doi.org/10.1234/example", None),
    ],
)
def test_route_only_recognized_unambiguous_paper_urls(url, provider):
    first = plan_lookups(entry(url), METHODS)[0]
    assert (first.provider if first.strategy == "url" else None) == provider


@pytest.mark.parametrize(
    ("title", "year", "correct"),
    [
        ("An Example Paper", "2024", True),
        ("An Example Paper", "2023", False),
        ("An Unrelated Paper", "2024", False),
    ],
)
def test_direct_resolution_compares_original_metadata_without_search(
    tmp_path, title, year, correct
):
    requests = []

    def respond(request):
        requests.append(str(request.url))
        assert str(request.url) == entry()["fields"]["url"]
        return httpx.Response(200, text=metadata(title, year))

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    try:
        result = lookup(entry(), METHODS["pmlr"], client)
    finally:
        client.close()
    assert resolved(result)
    assert _consensus_with_input([result], entry()["fields"])["is_correct"] is correct
    assert result["found_ref"]["title"] == title
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body", ["<h1>Welcome</h1>", '<meta name="citation_title" content="An Example Paper">']
)
def test_http_success_without_usable_paper_metadata_requires_fallback(tmp_path, body):
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    )
    try:
        assert not resolved(lookup(entry(), METHODS["pmlr"], client))
    finally:
        client.close()


@pytest.mark.parametrize(("status", "attempts"), [(503, 2), (404, 1), (403, 1)])
def test_only_transient_http_errors_are_retried(tmp_path, status, attempts):
    requests = []

    def respond(request):
        requests.append(request)
        return (
            httpx.Response(status) if len(requests) == 1 else httpx.Response(200, text=metadata())
        )

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    stop = threading.Event()
    providers = {"pmlr": METHODS["pmlr"]}
    worker = ProviderLookup(client, providers, stop, SimpleQueue())
    try:
        with ProviderQueues(
            tmp_path / "queues", worker, providers=providers, stop=stop, retry_delay=0
        ) as queues:
            step = plan_lookups(entry(), providers)[0]
            result = queues.submit(entry(), "pmlr", asdict(step)).get(blocking=True, timeout=5)
    finally:
        client.close()
    assert len(requests) == attempts
    assert result["status"] == (
        "found" if attempts == 2 else "not_found" if status == 404 else "error"
    )


def test_provider_workers_overlap_and_each_provider_is_serial(tmp_path):
    advanced = threading.Event()
    guard = threading.Lock()
    active, maximum = Counter(), Counter()

    def retrieve(item, provider, phase, state):
        with guard:
            active[provider] += 1
            maximum[provider] = max(maximum[provider], active[provider])
        try:
            if provider == "arxiv":
                assert advanced.wait(5), "PMLR was blocked by arXiv"
            elif item["key"] == "pmlr2":
                advanced.set()
            return {"key": item["key"]}
        finally:
            with guard:
                active[provider] -= 1

    with ProviderQueues(tmp_path, retrieve) as queues:
        futures = [
            queues.submit({"key": key}, provider, "search")
            for key, provider in [("arxiv1", "arxiv"), ("pmlr1", "pmlr"), ("pmlr2", "pmlr")]
        ]
        assert len([future.get(blocking=True, timeout=5) for future in futures]) == 3
    assert maximum == {"arxiv": 1, "pmlr": 1}


def test_duplicate_keys_are_rejected_before_submission(tmp_path):
    report = {
        "schema_version": 3,
        "summary": {},
        "verification_scope": {"mode": "all", "eligible_keys": ["example"]},
        "items": [{"entry": entry(), "validations": {}}, {"entry": entry(), "validations": {}}],
    }
    source = tmp_path / "refs.json"
    source.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Duplicate"):
        run_audit(source, output=tmp_path / "audit")
    assert not (tmp_path / "audit/report.tmp.queues").exists()


def test_consumers_preserve_signal_handlers_and_stop_all_threads(tmp_path):
    handlers = {
        sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    }
    threads = set(threading.enumerate())
    with ProviderQueues(tmp_path, lambda *args: {"ok": True}) as queues:
        assert queues.submit({}, "pmlr", "search").get(blocking=True, timeout=5) == {"ok": True}
        assert all(signal.getsignal(sig) == handler for sig, handler in handlers.items())
    assert set(threading.enumerate()) == threads


def test_two_consumers_cannot_own_the_same_directory(tmp_path):
    with ProviderQueues(tmp_path, lambda *args: {}):
        with pytest.raises(ReportLockError):
            with ProviderQueues(tmp_path, lambda *args: {}):
                pass


def test_missing_input_title_requires_review(tmp_path):
    item = entry()
    del item["fields"]["title"]
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata()))
    )
    try:
        result = lookup(item, METHODS["pmlr"], client)
    finally:
        client.close()
    assert _consensus_with_input([result], item["fields"])["is_correct"] is None


def test_unverified_secondary_locator_is_not_hidden_by_a_primary_url(tmp_path):
    item = entry(openreview="OtherPaper")
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata()))
    )
    try:
        result = lookup(item, METHODS["pmlr"], client)
    finally:
        client.close()
    result = _consensus_with_input([result], item["fields"])
    assert result["is_correct"] is None
    assert any(f["code"] == "unverified_identifier" for f in result["input_findings"])


def test_benchmark_uses_production_queues_and_counts_tasks(tmp_path):
    from evaluation.url_first_benchmark import benchmark

    result = benchmark(tmp_path, citations=12)
    assert result["url_first"]["submitted"] == 12
    assert result["all_sources"]["submitted"] == 72
    assert result["url_first"]["database_bytes"] > 0
    assert result["url_first"]["extra_threads"] == 12
