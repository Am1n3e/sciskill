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


def test_proven_direct_discrepancy_settles_lookup_even_without_year():
    assert resolved(
        {
            "authority": True,
            "lookup_complete": True,
            "found_ref": {"title": "Another Paper", "authors": [{"family": "Smith"}]},
            "differences": [{"field": "title", "result": "mismatch"}],
        }
    )


@pytest.mark.parametrize("status", ["ambiguous", "found"])
def test_fallback_preserves_prior_locator_outcomes_and_gates_correct(status):
    from support import ENTRY, RECORD

    from bib_lint.verification import _consensus_with_input, _merge_lookup
    from bib_lint.verification.matching import select_result
    from bib_lint.verification.routing import LookupStep

    prior = {
        "name": "pmlr",
        "status": status,
        "authority": True,
        "found_ref": None,
        "candidates": [{**RECORD, "title": "Other Paper"}],
        "differences": [
            {
                "field": "title",
                "result": "mismatch",
                "input": RECORD["title"],
                "found": "Other Paper",
            }
        ],
    }
    direct = LookupStep("pmlr", "url", "https://proceedings.mlr.press/v235/other.html")
    methods = _merge_lookup([], prior, direct, {"pmlr": METHODS["pmlr"]})
    found = select_result("pmlr", RECORD, [RECORD], authority=True)
    methods = _merge_lookup(methods, found, LookupStep("pmlr", "search"), {"pmlr": METHODS["pmlr"]})
    assert methods[0]["lookup_history"][0]["candidates"][0]["title"] == "Other Paper"
    result = _consensus_with_input(methods, ENTRY["fields"])
    assert result["is_correct"] is None
    assert any(f["code"] == "earlier_locator_evidence" for f in result["input_findings"])


@pytest.mark.parametrize(
    ("url", "provider", "expected"),
    [
        (
            "https://proceedings.mlr.press/v235/example24a/example24a.pdf",
            "pmlr",
            "https://proceedings.mlr.press/v235/example24a.html",
        ),
        (
            "https://aclanthology.org/2024.acl-long.1.pdf",
            "acl_anthology",
            "https://aclanthology.org/2024.acl-long.1/",
        ),
        (
            "https://proceedings.neurips.cc/paper/2024/file/abc-Paper.pdf",
            "neurips",
            "https://proceedings.neurips.cc/paper/2024/hash/abc-Abstract.html",
        ),
        (
            "https://jmlr.org/papers/v25/24-001/24-001.pdf",
            "jmlr",
            "https://jmlr.org/papers/v25/24-001.html",
        ),
    ],
)
def test_provider_pdf_urls_route_to_metadata_pages(url, provider, expected):
    item = citation(url=url)
    query = plan_lookups(item, METHODS)[0].query(LookupQuery.from_entry(item))
    assert METHODS[provider].direct_url(query) == expected
