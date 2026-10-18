from dataclasses import replace

import httpx
import pytest
from provider_support import FixtureProvider

from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import Candidate, RequestPolicy


def context(tmp_path, respond, **policy):
    descriptor = replace(FixtureProvider().descriptor, request_policy=RequestPolicy(**policy))
    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    return RequestContext(client, descriptor, "A"), client


def test_redirect_hosts_credentials_and_https(tmp_path):
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://outside.test/paper"})

    ctx, client = context(tmp_path, respond)
    with pytest.raises(LookupFailure, match="declared source"):
        ctx.get("http://fixture.test/a")
    assert calls == ["https://fixture.test/a"]
    for url in ["https://u:p@fixture.test/a", "https://fixture.test:999/a", "file:///a"]:
        with pytest.raises(LookupFailure):
            ctx.get(url)
    client.close()


def test_internal_redirect_cache_and_page_budget(tmp_path):
    calls = []

    def respond(request):
        calls.append(str(request.url))
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "/b"})
        return httpx.Response(200, json={"title": "Paper"})

    ctx, client = context(tmp_path, respond, max_pages=2)
    assert ctx.json("https://fixture.test/a", page=True)["title"] == "Paper"
    assert ctx.json("https://fixture.test/b", page=True)["title"] == "Paper"
    assert ctx.evidence[-1]["cached"] and ctx.attempts == 2 and ctx.pages == 2
    with pytest.raises(LookupFailure, match="page budget"):
        ctx.get("https://fixture.test/b", page=True)
    assert len(calls) == 2
    client.close()


@pytest.mark.parametrize(
    "policy,expected",
    [
        ({"max_fetches": 1}, "fetch budget"),
        ({"max_attempts": 1}, "attempt budget"),
        ({"max_redirects": 1}, "redirects"),
    ],
)
def test_budgets(tmp_path, policy, expected):
    redirect = "max_redirects" in policy
    ctx, client = context(
        tmp_path,
        lambda _: httpx.Response(
            302 if redirect else 200, headers={"Location": "/loop"}, text="OK"
        ),
        **policy,
    )
    with pytest.raises(LookupFailure, match=expected):
        ctx.get("https://fixture.test/a")
        ctx.get("https://fixture.test/b")
    client.close()


def test_candidate_budget_and_storage_failure(tmp_path, monkeypatch):
    ctx, client = context(tmp_path, lambda _: httpx.Response(200, text="OK"), max_candidates=1)
    candidate = Candidate("Paper", url="https://fixture.test/a", provenance=(("source", "page"),))
    assert ctx.shortlist(candidate) == candidate
    with pytest.raises(LookupFailure, match="Candidate budget"):
        ctx.shortlist(candidate)
    monkeypatch.setattr(client.cache, "save", lambda *args: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        ctx.get("https://fixture.test/a")
    client.close()


def test_configured_pacing_retries_and_timeout(tmp_path, monkeypatch):
    from bib_lint.verification import http

    sleeps = []
    clock = [100.0]
    monkeypatch.setattr(http.time, "monotonic", lambda: clock[0])

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(http.time, "sleep", sleep)
    calls = []

    def respond(request):
        assert request.extensions["timeout"]["read"] == 7
        calls.append(request)
        return httpx.Response(503 if len(calls) < 3 else 200, text="OK")

    ctx, client = context(tmp_path, respond, interval=3.1, timeout=7)
    assert ctx.get("https://fixture.test/a") == "OK"
    assert sleeps == [2, pytest.approx(1.1), 4]
    assert ctx.attempts == 3
    client.close()


def test_malformed_json_and_attempt_retry_limit(tmp_path):
    ctx, client = context(tmp_path, lambda _: httpx.Response(200, text="<html>"))
    with pytest.raises(LookupFailure, match="valid JSON"):
        ctx.json("https://fixture.test/a")
    client.close()
    ctx, client = context(tmp_path / "retry", lambda _: httpx.Response(429), max_attempts=2)
    with pytest.raises(LookupFailure, match="attempt budget"):
        ctx.get("https://fixture.test/a")
    assert ctx.attempts == 2
    client.close()
