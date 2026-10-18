import json
from dataclasses import FrozenInstanceError, replace

import pytest
from provider_support import FixtureProvider, assert_contract
from support import ENTRY

from bib_lint.verification.providers.protocol import (
    Applicability,
    Candidate,
    LookupAttempt,
    LookupQuery,
    LookupResult,
    RequestPolicy,
)
from bib_lint.verification.providers.registry import validate_registry


def test_immutable_query_and_unknown_candidate():
    query = LookupQuery.from_entry(ENTRY)
    assert query.as_record()["title"] == ENTRY["fields"]["title"]
    assert dict(query.fields) == ENTRY["fields"]
    with pytest.raises(FrozenInstanceError):
        query.title = "Mutated"
    candidate = Candidate(None, url="https://fixture.test/paper", provenance=(("source", "note"),))
    assert candidate.as_record()["authors"] == []
    assert candidate.as_record()["year"] is None
    assert candidate.as_record()["publication_status"] == "unknown"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": []},
        {"year": True},
        {"authors": [None]},
        {"identifiers": (("a", 1),)},
        {"provenance": ()},
        {"url": "http://fixture.test"},
        {"record_type": "invented"},
        {"publication_status": "assumed"},
        {"venue": 1},
        {"version": 2},
    ],
)
def test_invalid_candidates(changes):
    candidate = Candidate("Title", url="https://fixture.test", provenance=(("source", "note"),))
    with pytest.raises(ValueError):
        replace(candidate, **changes).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"max_pages": 0},
        {"timeout": float("inf")},
        {"interval": -1},
        {"max_attempts": True},
        {"backoffs": (-1,)},
        {"backoffs": (float("nan"),)},
    ],
)
def test_invalid_policy(changes):
    with pytest.raises(ValueError):
        replace(RequestPolicy(), **changes).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "Unsafe/ID"},
        {"display_name": ""},
        {"adapter_version": ""},
        {"evidence_category": "vote"},
        {"allowed_hosts": ("*.example.org",)},
        {"canonical_priority": "first"},
        {"discovery_config": (("a", "b"), ("a", "c"))},
    ],
)
def test_invalid_descriptors(changes):
    with pytest.raises(ValueError):
        replace(FixtureProvider().descriptor, **changes).validate()


def test_registry_serialization_and_duplicate_validation():
    provider = FixtureProvider()
    registry = validate_registry([provider])
    descriptor = registry["fixture"].descriptor.serialize()
    assert json.loads(json.dumps(descriptor)) == descriptor
    with pytest.raises(ValueError, match="Duplicate"):
        validate_registry([provider, provider])
    with pytest.raises(ValueError, match="ProviderDescriptor"):
        validate_registry([lambda *_: None])
    with pytest.raises(ValueError, match="keys"):
        validate_registry({"wrong": provider})

    class Missing:
        descriptor = provider.descriptor

    with pytest.raises(ValueError, match="applicability"):
        validate_registry([Missing()])


def test_reusable_conformance_with_different_payload():
    query = LookupQuery.from_entry(ENTRY)
    provider = FixtureProvider(
        payload={
            "heading": "An Example Paper",
            "people": [{"given": "Jane", "family": "Smith"}],
            "date": 2025,
            "journal": "Example Journal",
            "ids": {"doi": "10.1234/example"},
        }
    )
    result = assert_contract(provider, query, None)
    assert result.candidates[0].year == 2025
    assert assert_contract(FixtureProvider(), query, None).candidates == ()
    with pytest.raises(KeyError):
        assert_contract(FixtureProvider(payload={}), query, None)


def test_result_validation_and_applicability():
    Applicability("inapplicable", "No supported input").validate()
    for result in [
        LookupResult(complete="yes"),
        LookupResult(candidates=(None,)),
        LookupResult(attempts=(LookupAttempt("", "scope"),)),
        LookupResult(attempts=(LookupAttempt("search", "scope", complete=False),)),
    ]:
        with pytest.raises(ValueError):
            result.validate()
    with pytest.raises(ValueError):
        Applicability("maybe").validate()
