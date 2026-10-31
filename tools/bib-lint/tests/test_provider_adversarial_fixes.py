"""Adversarial regressions for source locators, independent of citation hints."""

import copy
import json
from dataclasses import replace

import httpx
import pytest
from metadata_support import entry, html_record, write_bib
from pybtex.database import BibliographyData
from pybtex.database import parse_file as pybtex_parse_file

from bib_lint.audit import run_audit
from bib_lint.status import reference_status
from bib_lint.verification import verify_reference
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers import jmlr as jmlr_module
from bib_lint.verification.providers.archive import ArchiveProvider
from bib_lint.verification.providers.protocol import LookupQuery

KEY = "JMLR:v22:20-1364"
ABSTRACT = "https://jmlr.org/papers/v22/20-1364.html"
PDF = "https://jmlr.org/papers/volume22/20-1364/20-1364.pdf"


def source_entry(url=ABSTRACT):
    source = entry(KEY)
    source["fields"]["url"] = url
    return source


def input_bibliography(tmp_path, url=ABSTRACT):
    path = write_bib(tmp_path / "refs.bib", KEY)
    source = pybtex_parse_file(str(path)).entries[KEY]
    source.fields.update(url=url, volume="999")
    BibliographyData(entries={KEY: source}).to_file(str(path))
    return path


@pytest.mark.parametrize(
    "url",
    [
        PDF,
        PDF.replace("https://", "http://"),
        PDF.replace("jmlr.org", "www.jmlr.org"),
        PDF + "?download=1#page=3",
        "https://jmlr.org/papers/v22/20-1364.pdf",
    ],
)
def test_jmlr_official_pdf_locator_precedes_bad_volume(tmp_path, url):
    """An official PDF contains stronger routing context than an unchecked volume."""
    bibliography = input_bibliography(tmp_path, url)
    original = bibliography.read_bytes()
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert str(request.url) == ABSTRACT, "Do not fetch a PDF or an unrelated volume"
        return httpx.Response(200, text=html_record("sb3"))

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(
            bibliography, output=tmp_path / "audit", client=client, methods=[METHODS["jmlr"]]
        )
    finally:
        client.close()
    item = report["items"][0]
    method = item["validations"]["correctness"]["methods"][0]
    assert reference_status(item["validations"]) == "Correct"
    assert method["source_url"] == ABSTRACT
    assert method["found_ref"]["identifiers"]["jmlr"] == "v22/20-1364"
    assert calls == [ABSTRACT]
    assert bibliography.read_bytes() == original


@pytest.mark.parametrize("missing_status", [200, 404])
def test_jmlr_unproductive_volume_falls_back_to_independent_year_catalog(tmp_path, missing_status):
    source = source_entry()
    for field in ("url", "jmlr", "jmlr_id"):
        source["fields"].pop(field, None)
    source["fields"]["volume"] = "999"
    calls = []

    def respond(request):
        url = str(request.url)
        calls.append(url)
        if url == "https://jmlr.org/papers/v999/":
            return httpx.Response(missing_status, text="<html>No matching papers</html>")
        if url == "https://jmlr.org/papers/":
            return httpx.Response(200, text='<a href="v22/">Volume 22 (2021)</a>')
        if url == "https://jmlr.org/papers/v22/":
            title = source["fields"]["title"]
            return httpx.Response(200, text=f'<a href="20-1364.html">{title}</a>')
        assert url == ABSTRACT
        return httpx.Response(200, text=html_record("sb3"))

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        result = verify_reference(source, client, methods=[METHODS["jmlr"]])
    finally:
        client.close()
    method = result["methods"][0]
    assert method["status"] == "found"
    assert method["found_ref"]["identifiers"]["jmlr"] == "v22/20-1364"
    assert calls == [
        "https://jmlr.org/papers/v999/",
        "https://jmlr.org/papers/",
        "https://jmlr.org/papers/v22/",
        ABSTRACT,
    ]
    assert source["fields"]["volume"] == "999"


@pytest.mark.parametrize(
    "value",
    [
        "v22/20-1364",
        "volume22/20-1364",
        "v22/20-1364.html",
        "v22/%32%30-1364",
        "papers/v22/20-1364",
        "/papers/volume22/20-1364.html",
        ABSTRACT,
        "https://jmlr.org/papers/v22/%32%30-1364.html",
        "http://www.jmlr.org/papers/volume22/20-1364.html",
        PDF,
        "https://jmlr.org/papers/v22/20-1364.pdf",
    ],
)
def test_jmlr_identifier_equates_official_aliases(value):
    assert jmlr_module.jmlr_identifier(value) == "v22/20-1364"


@pytest.mark.parametrize(
    "value",
    [
        "https://jmlr.org.evil.example/papers/volume22/20-1364/20-1364.pdf",
        "https://evil.example/papers/v22/20-1364.html",
        "https://%6Amlr.org/papers/v22/20-1364.html",
        "//jmlr.org/papers/v22/20-1364.html",
        "ftp://jmlr.org/papers/v22/20-1364.html",
        "https://user:password@jmlr.org/papers/v22/20-1364.html",
        "https://jmlr.org:9999/papers/v22/20-1364.html",
        "https://jmlr.org:invalid/papers/v22/20-1364.html",
        "https://jmlr.org/download/20-1364.pdf",
        "https://jmlr.org/v22/20-1364.html",
        "https://jmlr.org/papers/volume22/other/20-1364.pdf",
        "https://jmlr.org/papers/volume22/20-1364/%2E%2E.pdf",
        "v22/../20-1364",
        "v22/20-1364?other-paper",
    ],
)
def test_jmlr_identifier_rejects_untrusted_or_unrelated_locations(value):
    assert jmlr_module.jmlr_identifier(value) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@jmlr.org/papers/volume22/20-1364/20-1364.pdf",
        "ftp://jmlr.org/papers/volume22/20-1364/20-1364.pdf",
        "https://jmlr.org:9999/papers/volume22/20-1364/20-1364.pdf",
    ],
)
def test_jmlr_pdf_conversion_does_not_bypass_source_url_policy(url):
    query = LookupQuery.from_entry(source_entry(url))
    with pytest.raises(LookupFailure, match="Nonstandard source URL"):
        METHODS["jmlr"].direct_url(query)


@pytest.mark.parametrize(
    "url",
    [
        ABSTRACT,
        "https://jmlr.org/papers/volume22/20-1364.html",
        "http://www.jmlr.org/papers/volume22/20-1364.html",
    ],
)
def test_jmlr_retrieved_identifier_is_stable_across_legacy_urls(tmp_path, url):
    client = MetadataClient(
        tmp_path,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=html_record("sb3"))),
    )
    try:
        result = verify_reference(source_entry(url), client, methods=[METHODS["jmlr"]])
    finally:
        client.close()
    assert result["is_correct"] is True
    assert result["canonical_ref"]["identifiers"]["jmlr"] == "v22/20-1364"


def test_jmlr_adapter_upgrade_reuses_evidence_and_recomputes_locator(tmp_path):
    bibliography = input_bibliography(tmp_path)
    legacy = copy.copy(METHODS["jmlr"])
    legacy.descriptor = replace(legacy.descriptor, adapter_version="2")
    legacy.identifiers = lambda url: ArchiveProvider.identifiers(legacy, url)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=html_record("sb3"))

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        workspace, first, _ = run_audit(
            bibliography, output=tmp_path / "audit", client=client, methods=[legacy]
        )
        old = first["items"][0]["validations"]["correctness"]
        assert old["canonical_ref"]["identifiers"]["jmlr"] == "papers/v22/20-1364"
        manifest = json.loads((workspace.cache / "checksum.json").read_text())
        raw = {r["path"]: (workspace.cache / r["path"]).read_bytes() for r in manifest["files"]}
        _, second, _ = run_audit(
            bibliography, output=tmp_path / "audit", client=client, methods=[METHODS["jmlr"]]
        )
    finally:
        client.close()
    result = second["items"][0]["validations"]["correctness"]
    assert result["canonical_ref"]["identifiers"]["jmlr"] == "v22/20-1364"
    assert calls == [ABSTRACT]
    assert result["methods"][0]["requests"][0]["cached"]
    assert all((workspace.cache / path).read_bytes() == data for path, data in raw.items())
