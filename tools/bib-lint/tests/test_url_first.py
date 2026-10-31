"""Contracts for the opt-in URL-first/Huey experiment."""

import threading
from collections import Counter

import httpx
import pytest

from bib_lint.storage import ReportLockError
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.providers import METHODS
from evaluation.provider_queues import ProviderQueues
from evaluation.url_first import lookup_entry, route_url, run_entries


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
    assert route_url(entry(url)) == provider


@pytest.mark.parametrize(
    ("title", "year", "status"),
    [
        ("An Example Paper", "2024", "verified"),
        ("An Example Paper", "2023", "mismatch"),
        ("An Unrelated Paper", "2024", "mismatch"),
    ],
)
def test_direct_resolution_compares_the_original_citation_without_search(
    tmp_path, title, year, status
):
    requests = []

    def respond(request):
        requests.append(str(request.url))
        assert str(request.url) == entry()["fields"]["url"]
        return httpx.Response(200, text=metadata(title, year))

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    try:
        result = lookup_entry(entry(), METHODS["pmlr"], "direct", client)
    finally:
        client.close()
    assert result["outcome"] == "resolved"
    assert result["status"] == status
    assert result["record"]["title"] == title
    assert len(requests) == 1


def test_successful_html_response_without_paper_metadata_is_unresolved(tmp_path):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<h1>Welcome</h1>")),
    )
    try:
        result = lookup_entry(entry(), METHODS["pmlr"], "direct", client)
    finally:
        client.close()
    assert result["outcome"] == "unresolved"


def test_direct_resolution_with_incomplete_metadata_requires_fallback(tmp_path):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, text='<meta name="citation_title" content="An Example Paper">'
            )
        ),
    )
    try:
        result = lookup_entry(entry(), METHODS["pmlr"], "direct", client)
    finally:
        client.close()
    assert result["outcome"] == "unresolved"


def test_one_hundred_resolved_urls_schedule_one_hundred_tasks(tmp_path):
    entries = [{**entry(), "key": str(i)} for i in range(100)]
    calls = Counter()

    def lookup(item, provider, phase):
        calls[(provider, phase)] += 1
        return {"outcome": "resolved", "status": "verified", "key": item["key"]}

    with ProviderQueues(tmp_path, lookup) as queues:
        result = run_entries(entries, queues)
    assert len(result) == 100
    assert calls == {("pmlr", "direct"): 100}
    assert queues.submitted == 100


def test_direct_failure_schedules_discovery_only_when_needed(tmp_path):
    calls = []

    def lookup(item, provider, phase):
        calls.append((provider, phase))
        return {
            "outcome": "resolved" if phase == "search" else "unresolved",
            "status": "verified",
        }

    with ProviderQueues(tmp_path, lookup) as queues:
        result = run_entries([entry()], queues)
    assert calls == [("pmlr", "direct"), ("pmlr", "search")]
    assert len(result["example"]["attempts"]) == 2


def test_missing_url_uses_lazy_discovery_without_six_way_fanout(tmp_path):
    calls = []

    def lookup(item, provider, phase):
        calls.append((provider, phase))
        return {"outcome": "resolved", "status": "verified"}

    with ProviderQueues(tmp_path, lookup) as queues:
        result = run_entries([entry("")], queues)
    assert result["example"]["status"] == "verified"
    assert calls == [("arxiv", "search")]


def test_provider_workers_overlap_but_each_provider_is_serial(tmp_path):
    other_provider_advanced = threading.Event()
    guard = threading.Lock()
    active, maximum = Counter(), Counter()

    def lookup(item, provider, phase):
        with guard:
            active[provider] += 1
            maximum[provider] = max(maximum[provider], active[provider])
        try:
            if provider == "arxiv":
                assert other_provider_advanced.wait(5), "PMLR was blocked behind arXiv"
            elif item["key"] == "pmlr2":
                other_provider_advanced.set()
            return {"outcome": "resolved", "status": "verified"}
        finally:
            with guard:
                active[provider] -= 1

    entries = [
        {**entry("https://arxiv.org/abs/2401.12345"), "key": "arxiv1"},
        {**entry(), "key": "pmlr1"},
        {**entry(), "key": "pmlr2"},
    ]
    with ProviderQueues(tmp_path, lookup) as queues:
        result = run_entries(entries, queues)
    assert len(result) == 3
    assert maximum == {"arxiv": 1, "pmlr": 1}


@pytest.mark.parametrize(("code", "attempts"), [("network_error", 2), ("not_found", 1)])
def test_huey_retries_transient_failures_but_not_missing_papers(tmp_path, code, attempts):
    calls = []

    def lookup(item, provider, phase):
        calls.append(phase)
        if len(calls) == 1:
            raise LookupFailure(code, "fixture failure")
        return {"outcome": "resolved", "status": "verified"}

    with ProviderQueues(tmp_path, lookup, retries=1, retry_delay=1) as queues:
        result = queues.submit(entry(), "pmlr", "direct").get(blocking=True, timeout=5)
    assert len(calls) == attempts
    assert result["outcome"] == ("resolved" if attempts == 2 else "unresolved")


def test_local_storage_failure_is_fatal_without_retry_or_discovery(tmp_path):
    calls = []

    def lookup(*args):
        calls.append(args)
        raise OSError("disk full")

    with ProviderQueues(tmp_path, lookup) as queues:
        with pytest.raises(RuntimeError, match="disk full"):
            run_entries([entry()], queues)
    assert len(calls) == 1


def test_duplicate_citation_keys_are_rejected_before_submission(tmp_path):
    with ProviderQueues(tmp_path, lambda *_: None) as queues:
        with pytest.raises(ValueError, match="Duplicate"):
            run_entries([entry(), entry()], queues)
    assert queues.submitted == 0


def test_sqlite_pending_task_survives_queue_recreation(tmp_path):
    def lookup(item, provider, phase):
        return {"outcome": "resolved", "status": "verified", "key": item["key"]}

    original = ProviderQueues(tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]})
    future = original.submit(entry(), "pmlr", "direct")
    original.queues["pmlr"].storage.close()
    with ProviderQueues(tmp_path, lookup, providers={"pmlr": METHODS["pmlr"]}):
        result = future.get(blocking=True, timeout=5)
    assert result["key"] == "example"


def test_real_direct_mismatch_finishes_without_discovery(tmp_path):
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, text=metadata("An Unrelated Paper"))

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))

    def lookup(item, provider, phase):
        assert provider == "pmlr" and phase == "direct"
        return lookup_entry(item, METHODS[provider], phase, client)

    try:
        with ProviderQueues(tmp_path / "queues", lookup) as queues:
            result = run_entries([entry()], queues)
    finally:
        client.close()
    assert result["example"]["status"] == "mismatch"
    assert requests == [entry()["fields"]["url"]]


def test_arxiv_url_retrieval_does_not_follow_conflicting_eprint(tmp_path):
    requests = []
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<id>https://arxiv.org/abs/2401.12345</id><title>An Example Paper</title>"
        "<author><name>Jane Smith</name></author><published>2024-01-01</published>"
        "</entry></feed>"
    )

    def respond(request):
        requests.append(request)
        assert dict(request.url.params) == {"id_list": "2401.12345"}
        return httpx.Response(200, text=atom)

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    try:
        result = lookup_entry(
            entry("https://arxiv.org/abs/2401.12345", eprint="2402.54321"),
            METHODS["arxiv"],
            "direct",
            client,
        )
    finally:
        client.close()
    assert result["status"] == "mismatch"
    assert any(
        finding.get("code") == "conflicting_identifiers"
        for comparison in result["comparisons"]
        for finding in comparison.get("input_findings", [])
    )
    assert len(requests) == 1


def test_embedded_consumers_restore_signal_handlers_and_stop_threads(tmp_path):
    import signal

    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    threads = set(threading.enumerate())
    with ProviderQueues(tmp_path, lambda *_: {"outcome": "resolved"}) as queues:
        run_entries([entry()], queues)
        assert all(signal.getsignal(sig) == handler for sig, handler in before.items())
    assert set(threading.enumerate()) == threads


def test_benchmark_measures_lazy_routing_and_full_fanout(tmp_path):
    from evaluation.url_first_benchmark import benchmark

    result = benchmark(tmp_path, citations=12)
    assert result["url_first"]["submitted"] == 12
    assert result["all_sources"]["submitted"] == 72
    assert result["url_first"]["database_bytes"] > 0
    assert result["url_first"]["extra_threads"] == 12


def test_two_consumers_cannot_own_the_same_prototype_directory(tmp_path):
    with ProviderQueues(tmp_path, lambda *_: None):
        with pytest.raises(ReportLockError):
            with ProviderQueues(tmp_path, lambda *_: None):
                pass


def test_missing_input_title_requires_review_instead_of_a_mismatch(tmp_path):
    item = entry()
    del item["fields"]["title"]
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata()))
    )
    try:
        result = lookup_entry(item, METHODS["pmlr"], "direct", client)
    finally:
        client.close()
    assert result["outcome"] == "resolved"
    assert result["status"] == "needs_review"


def test_unverified_secondary_locator_is_not_hidden_by_a_valid_primary_url(tmp_path):
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata()))
    )
    try:
        result = lookup_entry(entry(openreview="OtherPaper"), METHODS["pmlr"], "direct", client)
    finally:
        client.close()
    assert result["status"] == "needs_review"
    assert any(f["code"] == "unverified_identifier" for f in result["input_findings"])
