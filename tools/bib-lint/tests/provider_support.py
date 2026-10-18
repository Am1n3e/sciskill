"""Reusable retrieval contract harness and trusted fixture providers."""

from bib_lint.verification.providers.protocol import (
    Applicability,
    Candidate,
    LookupAttempt,
    LookupResult,
    ProviderDescriptor,
)


class FixtureProvider:
    """An extension with a deliberately different payload shape, for offline tests."""

    def __init__(self, name="fixture", payload=None, *, version="1", lookup=None):
        self.descriptor = ProviderDescriptor(
            name, "Fixture publication source", version, "publication_archive", ("fixture.test",)
        )
        self.payload = payload
        self.retrieval = lookup

    def applicability(self, query):
        return Applicability(strategies=("fixture",))

    def lookup(self, query, context):
        if self.retrieval:
            return self.retrieval(query, context)
        payload = self.payload
        records = (
            []
            if payload is None
            else [
                Candidate.from_record(
                    {
                        "title": payload["heading"],
                        "authors": payload.get("people", []),
                        "year": payload.get("date"),
                        "venue": payload.get("journal"),
                        "identifiers": payload.get("ids", {}),
                        "url": "https://fixture.test/paper",
                        "record_type": "publication",
                        "publication_status": "published",
                    },
                    provenance={"source": "https://fixture.test/paper"},
                )
            ]
        )
        return LookupResult(tuple(records), (LookupAttempt("fixture", "https://fixture.test"),))


def assert_contract(provider, query, context):
    """Any provider with representative fake responses can use these invariants."""
    provider.descriptor.validate()
    applicability = provider.applicability(query)
    applicability.validate()
    if applicability.state == "applicable":
        result = provider.lookup(query, context)
        result.validate()
        assert len(result.candidates) <= provider.descriptor.request_policy.max_candidates
        assert all(c.url and c.provenance for c in result.candidates)
        return result
    return applicability


def fixture_registry(methods):
    """Migrate old test fixtures to the retrieval contract, never a runtime adapter."""
    providers = []
    for name, function in methods.items():

        def lookup(query, context, function=function):
            outcome = function(query.as_record(), context)
            records = (
                [outcome["found_ref"]]
                if outcome.get("found_ref")
                else outcome.get("candidates", [])
            )
            candidates = []
            for record in records:
                record = {**record, "record_type": record.get("record_type", "publication")}
                record["publication_status"] = "published"
                record["url"] = record.get("url") or "https://fixture.test/paper"
                candidates.append(
                    Candidate.from_record(record, provenance={"source": record["url"]})
                )
            return LookupResult(
                tuple(candidates), (LookupAttempt("fixture", "https://fixture.test"),)
            )

        provider = FixtureProvider(name, lookup=lookup)
        providers.append(provider)
    return providers
