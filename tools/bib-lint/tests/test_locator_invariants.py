"""Equivalent scholarly locators must preserve identity and validation decisions."""

from contextlib import closing
from copy import deepcopy

import httpx
import pytest
from support import ENTRY, RECORD

from bib_lint.verification import verify_reference
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.input_checks import input_findings
from bib_lint.verification.matching import doi, input_record, select_result
from bib_lint.verification.providers import METHODS

# Expected identities are explicit, rather than derived with the normalizer under test.
URL_CASES = [
    ("arxiv", "2501.12345v2", "arxiv.org/abs/2501.12345v2"),
    ("arxiv", "2501.12345v2", "arxiv.org/pdf/2501.12345v2.pdf"),
    ("arxiv", "2501.12345v2", "arxiv.org/html/2501.12345v2"),
    ("arxiv", "2501.12345v2", "export.arxiv.org/abs/2501.12345v2"),
    ("arxiv", "2501.12345", "arxiv.org/abs/2501.12345"),
    ("arxiv", "math/0501234v1", "arxiv.org/abs/math/0501234v1"),
    ("doi", "10.1234/example", "doi.org/10.1234/example"),
    ("doi", "10.1234/example", "dx.doi.org/10.1234/example"),
    ("pmlr", "v250/example25a", "proceedings.mlr.press/v250/example25a.html"),
    ("pmlr", "v250/example25a", "proceedings.mlr.press/v250/example25a/example25a.pdf"),
    ("jmlr", "v26/25-001", "jmlr.org/papers/v26/25-001.html"),
    ("jmlr", "v26/25-001", "www.jmlr.org/papers/volume26/25-001/25-001.pdf"),
    ("acl", "2025.acl-long.1", "aclanthology.org/2025.acl-long.1/"),
    ("acl", "P19-1001", "aclanthology.org/P19-1001.pdf"),
    (
        "neurips",
        "paper_files/paper/2025/hash/ab12-Abstract-Conference",
        "proceedings.neurips.cc/paper_files/paper/2025/hash/ab12-Abstract-Conference.html",
    ),
    (
        "neurips",
        "paper_files/paper/2025/hash/ab12-Abstract-Conference",
        "papers.nips.cc/paper_files/paper/2025/file/ab12-Paper-Conference.pdf",
    ),
    ("openreview", "Example_25-a", "openreview.net/forum?id=Example_25-a"),
    ("openreview", "Example_25-a", "api2.openreview.net/notes?id=Example_25-a"),
]


def url_variant(address, scheme, encoded, decorated):
    host, path = address.split("/", 1)
    if encoded:
        path = path.replace(".", "%2E").replace("-", "%2D").replace("_", "%5F")
    url = f"{scheme}://{host.upper()}/{path}"
    if decorated:
        url += ("&" if "?" in url else "?") + "download=1#reference"
    return url


@pytest.mark.parametrize("provider,identifier,address", URL_CASES)
@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("encoded", [False, True], ids=["literal", "percent-encoded"])
@pytest.mark.parametrize("decorated", [False, True], ids=["plain", "query-and-fragment"])
def test_equivalent_official_urls_keep_correct_verdict(
    provider, identifier, address, scheme, encoded, decorated
):
    url = url_variant(address, scheme, encoded, decorated)
    entry = deepcopy(ENTRY)
    entry["fields"].pop("doi")
    entry["fields"].update(url=url, **{provider: identifier})
    if provider == "arxiv":
        entry["fields"].update(journal="arXiv", eprint=url)
    source = deepcopy(RECORD)
    source.update(identifiers={provider: identifier}, url=url)
    if provider == "arxiv":
        source.update(venue="arXiv", record_type="preprint")
    original = input_record(entry)
    findings = input_findings(entry["fields"])
    method = select_result("primary", original, [source], authority=True)
    assert not findings
    assert build_consensus([method], input_findings=findings)["is_correct"] is True
    if provider == "arxiv":
        assert original["identifiers"]["arxiv"] == identifier


@pytest.mark.parametrize("provider,identifier", list(dict.fromkeys(c[:2] for c in URL_CASES[8:16])))
def test_encoded_identifiers_from_sources_match_literal_input(provider, identifier):
    entry = deepcopy(ENTRY)
    entry["fields"][provider] = identifier
    source = deepcopy(RECORD)
    source["identifiers"][provider] = identifier.replace(".", "%2E").replace("-", "%2D")
    method = select_result("primary", input_record(entry), [source], authority=True)
    assert build_consensus([method])["is_correct"] is True


@pytest.mark.parametrize(
    "url",
    [
        "https:// arxiv.org/abs/2501.12345",
        "https://arxiv. org/abs/2501.12345",
        "https://arxiv.org/abs/2501.\t12345",
        "https://arxiv.org/abs/2501.\n12345",
        "https://arxiv.org/abs/2501.\x0012345",
        "https://arxiv.org/abs/2501.12345 extra",
        "https://[",
        "https://arxiv.org:invalid/abs/2501.12345",
        "https://user:pass@arxiv.org/abs/2501.12345",
        "arxiv.org/abs/2501.12345",
    ],
)
def test_malformed_urls_produce_review_findings(url):
    findings = input_findings({"url": url})
    assert any(f["field"] == "url" and f["code"] == "invalid_url" for f in findings)
    assert "arxiv" not in input_record({"fields": {"url": url}})["identifiers"]


@pytest.mark.parametrize("route", ["abs", "pdf", "html"])
@pytest.mark.parametrize("encoded", [False, True])
def test_url_only_arxiv_identity_survives_encoding(route, encoded):
    url = url_variant(f"arxiv.org/{route}/2501.12345v2", "https", encoded, True)
    assert input_record({"fields": {"url": url}})["identifiers"] == {"arxiv": "2501.12345v2"}


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/arxiv.org/abs/2501.12345",
        "https://example.test/?next=https://arxiv.org/abs/2501.12345",
        "https://arxiv.org.example.test/arxiv.org/abs/2501.12345",
        "https://user@arxiv.org/abs/2501.12345",
    ],
)
def test_untrusted_urls_do_not_supply_arxiv_routing_identity(url):
    assert "arxiv" not in input_record({"fields": {"url": url}})["identifiers"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10.1234/example?part#section", "10.1234/example?part#section"),
        (
            "https://doi.org/10.1234/example%3Fpart%23section?download=1#reference",
            "10.1234/example?part#section",
        ),
        ("https://doi.org/10.1234/example?download=1#reference", "10.1234/example"),
    ],
)
def test_doi_uri_delimiters_are_distinct_from_encoded_identifier_characters(value, expected):
    assert doi(value) == expected


@pytest.mark.parametrize("control", ["\t", "\n", "\r"])
def test_doi_uri_normalization_cannot_silently_erase_invalid_characters(control):
    value = f"https://doi.org/10.1234/exa{control}mple"
    assert any(f["code"] == "invalid_identifier" for f in input_findings({"doi": value}))


@pytest.mark.parametrize("route", ["abs", "pdf", "html"])
@pytest.mark.parametrize("encoded", [False, True])
def test_url_only_arxiv_routes_to_exact_version_without_title_fallback(tmp_path, route, encoded):
    entry = deepcopy(ENTRY)
    entry["fields"].pop("doi")
    entry["fields"].update(
        journal="arXiv",
        url=url_variant(f"arxiv.org/{route}/2501.12345v2", "https", encoded, True),
    )
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.host == "export.arxiv.org"
        assert dict(request.url.params) == {"id_list": "2501.12345v2"}
        return httpx.Response(
            200,
            text='<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<id>https://arxiv.org/abs/2501.12345v2</id><title>An Example Paper</title>"
            "<published>2025-01-01</published><author><name>Jane Smith</name></author>"
            "</entry></feed>",
        )

    with closing(
        MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    ) as client:
        result = verify_reference(entry, client, methods=[METHODS["arxiv"]])
    assert result["is_correct"] is True
    assert result["canonical_ref"]["identifiers"] == {"arxiv": "2501.12345v2"}
    assert len(calls) == 1
