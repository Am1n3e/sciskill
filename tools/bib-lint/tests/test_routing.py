"""Locator-first retrieval never substitutes input metadata for retrieved evidence."""

import httpx
import pytest

from bib_lint.verification import _source_result
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery
from bib_lint.verification.routing import plan_lookups, resolved


def citation(**fields):
    return {
        "key": "example",
        "fields": {"title": "An Example Paper", "year": "2024", **fields},
        "persons": {"author": [{"first": ["Jane"], "last": ["Smith"]}]},
    }


def test_url_precedes_conflicting_identifiers_and_discovery():
    item = citation(url="https://arxiv.org/abs/2401.12345", eprint="2402.54321")
    steps = plan_lookups(item, METHODS)
    assert [(s.provider, s.strategy, s.value) for s in steps[:2]] == [
        ("arxiv", "url", "https://arxiv.org/abs/2401.12345"),
        ("arxiv", "identifier", "2402.54321"),
    ]
    direct = steps[0].query(LookupQuery.from_entry(item))
    assert direct.title is None
    assert dict(direct.identifiers) == {"arxiv": "2401.12345"}
    assert all(step.strategy == "search" for step in steps[2:])


def test_identifier_only_reference_resolves_before_search():
    steps = plan_lookups(citation(eprint="2401.12345", archiveprefix="arXiv"), METHODS)
    assert (steps[0].provider, steps[0].strategy, steps[0].value) == (
        "arxiv",
        "identifier",
        "2401.12345",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org.evil.test/abs/2401.12345",
        "https://arxiv.org@evil.test/abs/2401.12345",
        "https://arxiv.org:8443/abs/2401.12345",
        "https://arxiv.org/search",
        "https://openreview.net/forum?id=one&id=two",
    ],
)
def test_untrusted_or_ambiguous_urls_do_not_create_direct_fetches(url):
    assert all(step.strategy == "search" for step in plan_lookups(citation(url=url), METHODS))


def test_url_and_equivalent_identifier_are_not_scheduled_twice():
    steps = plan_lookups(
        citation(url="https://arxiv.org/abs/2401.12345", eprint="2401.12345"), METHODS
    )
    assert [s.strategy for s in steps].count("url") == 1
    assert all(s.strategy != "identifier" for s in steps)


@pytest.mark.parametrize(
    ("title", "year"), [("An Unrelated Paper", "2024"), ("An Example Paper", "2023")]
)
def test_direct_record_discrepancies_use_shared_comparison_without_search(tmp_path, title, year):
    item = citation(url="https://proceedings.mlr.press/v235/example24a.html")
    query = LookupQuery.from_entry(item)
    step = plan_lookups(item, METHODS)[0]
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(
            200,
            text=(
                f'<meta name="citation_title" content="{title}">'
                '<meta name="citation_author" content="Jane Smith">'
                f'<meta name="citation_publication_date" content="{year}">'
            ),
        )

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    try:
        context = RequestContext(client, METHODS["pmlr"].descriptor, query.citation_key)
        result = _source_result(
            METHODS["pmlr"], query, context, retrieval=step.query(query), strategy=step.strategy
        )
    finally:
        client.close()
    assert resolved(result)
    assert result["status"] == "found"
    assert result["differences"]
    assert requests == [item["fields"]["url"]]
