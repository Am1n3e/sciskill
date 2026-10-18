import copy

import httpx
import pytest
from provider_support import fixture_registry
from support import ENTRY, RECORD, FakeClient

from bib_lint.verification import verify_reference
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.matching import (
    compare_fields,
    identity_match,
    same_record,
    select_result,
)
from bib_lint.verification.providers.protocol import RequestPolicy


@pytest.mark.parametrize(
    "authors, expected",
    [
        ([{"given": "John", "family": "Doe"}, {"given": "Jane", "family": "Smith"}], "mismatch"),
        ([{"given": "J.", "family": "Smith"}, {"given": "John", "family": "Doe"}], "unknown"),
        ([{"given": "Jane", "family": "Smith"}], "mismatch"),
    ],
)
def test_order_initials_and_missing_authors(authors, expected):
    original = {
        **RECORD,
        "authors": [{"given": "Jane", "family": "Smith"}, {"given": "John", "family": "Doe"}],
    }
    assert compare_fields(original, {**original, "authors": authors})[1]["result"] == expected


def test_corporate_names_accents_and_identifier_identity():
    original = {**RECORD, "authors": [{"family": "World Health Organization"}]}
    assert compare_fields(original, copy.deepcopy(original))[1]["result"] == "match"
    original = {**RECORD, "authors": [{"given": "José", "family": "García"}]}
    found = {**original, "authors": [{"given": r"Jos{\'e}", "family": r"Garc{\'i}a"}]}
    assert compare_fields(original, found)[1]["result"] == "match"
    assert not identity_match(RECORD, {**RECORD, "title": "Totally different research"})
    assert not same_record(RECORD, {**RECORD, "identifiers": {"doi": "10.1234/other"}})
    assert not identity_match({**RECORD, "identifiers": {}}, {**RECORD, "authors": []})


@pytest.mark.parametrize("field", ["title", "authors", "year"])
def test_missing_core_metadata_cannot_confirm(field):
    found = {**RECORD, field: None if field != "authors" else []}
    result = select_result("crossref", RECORD, [found], authority=True)
    assert build_consensus([result])["is_correct"] is None


def test_expiry_refresh_and_failed_response_never_success(tmp_path, monkeypatch):
    from bib_lint.verification import cache

    clock = [1000.0]
    monkeypatch.setattr(cache.time, "time", lambda: clock[0])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=b' {"original": true}\n')

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    assert client.json("https://example.org/data") == {"original": True}
    client.get("https://example.org/data")
    assert len(calls) == 1
    clock[0] += 7 * 86400
    client.get("https://example.org/data")
    assert len(calls) == 2
    client.refresh = True
    client.get("https://example.org/data")
    assert len(calls) == 3
    client.close()
    errors = []
    client = MetadataClient(
        tmp_path / "fail",
        transport=httpx.MockTransport(
            lambda request: errors.append(request) or httpx.Response(403, text="denied")
        ),
    )
    for _ in range(2):
        with pytest.raises(LookupFailure):
            client.get("https://example.org/data")
    assert len(errors) == 2
    client.close()


def test_pacing_has_controlled_clock(tmp_path, monkeypatch):
    from bib_lint.verification import http

    clock = [10.0]
    sleeps = []
    monkeypatch.setattr(http.time, "monotonic", lambda: clock[0])

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(http.time, "sleep", sleep)
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, text="OK"))
    )
    client.get("https://export.arxiv.org/a", policy=RequestPolicy(interval=3.1))
    client.get("https://export.arxiv.org/b", policy=RequestPolicy(interval=3.1))
    assert sleeps == [3.1]
    client.close()


def test_evidence_storage_error_is_execution_failure():
    def fail(*_):
        raise OSError("Cannot save response")

    with pytest.raises(OSError):
        verify_reference(ENTRY, FakeClient(), methods=fixture_registry({"test": fail}))
