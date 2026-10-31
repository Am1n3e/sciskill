"""Public audit uses locator-first queues and checkpoints, not a parallel side path."""

import json
import threading
from dataclasses import replace

import httpx
import pytest
from provider_support import FixtureProvider

from bib_lint.audit import run_audit
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers.protocol import RequestPolicy


def source(tmp_path, count=1):
    path = tmp_path / "references.bib"
    path.write_text(
        "\n".join(
            "@article{ref" + str(i) + ",title={An Example Paper},author={Jane Smith},"
            "year={2024},url={https://proceedings.mlr.press/v235/example24a.html}}"
            for i in range(count)
        )
    )
    return path


def metadata(title="An Example Paper"):
    return (
        f'<meta name="citation_title" content="{title}">'
        '<meta name="citation_author" content="Jane Smith">'
        '<meta name="citation_publication_date" content="2024">'
    )


@pytest.mark.parametrize(
    ("title", "correct"), [("An Example Paper", True), ("An Unrelated Paper", False)]
)
def test_public_audit_stops_at_a_resolved_url_and_resumes_without_requests(
    tmp_path, title, correct
):
    bib = source(tmp_path)
    requests = []

    def respond(request):
        requests.append(str(request.url))
        assert request.url.host == "proceedings.mlr.press"
        return httpx.Response(200, text=metadata(title))

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        workspace, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
        outcome = report["items"][0]["validations"]["correctness"]
        assert outcome["complete"]
        assert outcome["is_correct"] is correct
        assert [m["name"] for m in outcome["methods"]] == ["pmlr"]
        assert outcome["retrieval"]["resolved"]
        run_audit(bib, output=workspace.root, client=client)
        assert len(requests) == 1
    finally:
        client.close()


def test_audit_schedules_one_direct_lookup_per_reference(tmp_path):
    bib = source(tmp_path, count=100)
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "proceedings.mlr.press"
        return httpx.Response(200, text=metadata())

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    assert len(requests) == 100
    assert report["summary"]["verification"]["correct"] == 100
    assert all(len(i["validations"]["correctness"]["methods"]) == 1 for i in report["items"])


def test_completed_direct_result_is_written_to_the_canonical_report(tmp_path):
    bib = source(tmp_path)
    client = MetadataClient(
        tmp_path / "cache",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata())),
    )
    try:
        workspace, _, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    saved = json.loads(workspace.final.read_text())
    assert saved["verification_run"]["retrieval_policy"] == "locator-first-v1"
    assert saved["verification_run"]["complete"]


def test_interrupt_after_checkpoint_does_not_consume_the_same_result_twice(tmp_path):
    bib = source(tmp_path)
    requests, interrupted = [], []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=metadata())

    def progress(message):
        if message == "  pmlr: Found" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(KeyboardInterrupt):
            run_audit(bib, output=tmp_path / "audit", client=client, progress=progress)
        saved = json.loads((tmp_path / "audit/report.tmp.json").read_text())
        method = saved["items"][0]["validations"]["correctness"]["methods"][0]
        assert len(method["lookup_history"]) == len(method["requests"]) == 1
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    assert len(requests) == 1
    assert report["verification_run"]["complete"]


def test_checkpoint_write_failure_does_not_merge_a_completed_lookup_twice(tmp_path, monkeypatch):
    from bib_lint import verification

    bib = source(tmp_path)
    requests, failures = [], []
    write = verification._write_json

    def fail_once(path, report):
        result = report["items"][0]["validations"].get("correctness", {})
        if result.get("complete") and not failures:
            failures.append(True)
            raise OSError("checkpoint disk failure")
        return write(path, report)

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=metadata())

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        monkeypatch.setattr(verification, "_write_json", fail_once)
        with pytest.raises(OSError, match="checkpoint disk failure"):
            run_audit(bib, output=tmp_path / "audit", client=client)
        saved = json.loads((tmp_path / "audit/report.tmp.json").read_text())
        assert "correctness" not in saved["items"][0]["validations"]
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    method = report["items"][0]["validations"]["correctness"]["methods"][0]
    assert len(requests) == len(method["requests"]) == len(method["lookup_history"]) == 1
    assert method["requests"][0]["cached"]
    assert "lookup_history" not in method["lookup_history"][0]


def test_http_attempt_budget_covers_all_scheduled_retries(tmp_path):
    bib = source(tmp_path)
    requests = []

    def lookup(query, context):
        context.get("https://fixture.test/paper")
        raise AssertionError("The HTTP failure should abort this lookup")

    provider = FixtureProvider(lookup=lookup)
    provider.descriptor = replace(provider.descriptor, request_policy=RequestPolicy(max_attempts=2))

    def respond(request):
        requests.append(request)
        return httpx.Response(503)

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client, methods=[provider])
    finally:
        client.close()
    method = report["items"][0]["validations"]["correctness"]["methods"][0]
    assert method["error"]["code"] == "incomplete_search"
    assert len(requests) == len(method["requests"]) == 2


def test_real_provider_lanes_overlap_and_keep_evidence_scoped(tmp_path):
    bib = tmp_path / "references.bib"
    bib.write_text(
        "\n".join(
            "@article{" + key + ",title={An Example Paper},author={Jane Smith},"
            "year={2024},url={" + url + "}}"
            for key, url in [
                ("arxivref", "https://arxiv.org/abs/2401.12345"),
                ("pmlrref1", "https://proceedings.mlr.press/v235/one.html"),
                ("pmlrref2", "https://proceedings.mlr.press/v235/two.html"),
            ]
        )
    )
    advanced = threading.Event()

    def respond(request):
        if request.url.host == "export.arxiv.org":
            assert advanced.wait(5), "arXiv blocked the independent PMLR queue"
            return httpx.Response(
                200,
                text=(
                    '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                    "<id>https://arxiv.org/abs/2401.12345</id><title>An Example Paper</title>"
                    "<author><name>Jane Smith</name></author><published>2024-01-01</published>"
                    "</entry></feed>"
                ),
            )
        assert request.url.host == "proceedings.mlr.press"
        if request.url.path.endswith("two.html"):
            advanced.set()
        return httpx.Response(200, text=metadata())

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    assert report["summary"]["verification"]["correct"] == 3
    for item in report["items"]:
        method = item["validations"]["correctness"]["methods"][0]
        assert len(method["requests"]) == 1
        assert method["requests"][0]["cache_file"].startswith(item["entry"]["key"] + "/")


def test_doi_resolution_hands_off_to_the_metadata_provider_and_resumes(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{doi,title={An Example Paper},author={Jane Smith},year={2024},"
        "doi={10.1234/example}}"
    )
    requests, interrupted = [], []

    def respond(request):
        requests.append(str(request.url))
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://proceedings.mlr.press/v235/example24a.html"}
            )
        assert request.url.host == "proceedings.mlr.press"
        return httpx.Response(
            200, text=metadata() + '<meta name="citation_doi" content="10.1234/example">'
        )

    def progress(message):
        if message == "  doi: Not applicable" and not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(KeyboardInterrupt):
            run_audit(bib, output=tmp_path / "audit", client=client, progress=progress)
        assert requests == ["https://doi.org/10.1234/example"]
        _, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
    finally:
        client.close()
    assert len(requests) == 2
    correctness = report["items"][0]["validations"]["correctness"]
    assert correctness["is_correct"] is True
    assert correctness["retrieval"]["resolved"]
    assert [m["name"] for m in correctness["methods"]] == ["pmlr", "doi"]


@pytest.mark.parametrize(
    "destination",
    [
        "https://publisher.test/paper",
        "http://127.0.0.1:22/private",
        "file:///etc/passwd",
        "https://doi.org@evil.test/paper",
    ],
)
def test_doi_resolver_never_fetches_untrusted_destinations(tmp_path, destination):
    from bib_lint.verification.providers import METHODS

    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{doi,title={An Example Paper},author={Jane Smith},year={2024},"
        "doi={10.1234/example}}"
    )
    requests = []

    def respond(request):
        requests.append(str(request.url))
        assert request.url.host in {"doi.org", "proceedings.mlr.press"}
        if request.url.host == "doi.org":
            return httpx.Response(302, headers={"Location": destination})
        return httpx.Response(200, text="<h1>No catalog matches</h1>")

    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(respond))
    try:
        _, report, _ = run_audit(
            bib, output=tmp_path / "audit", client=client, methods=[METHODS["pmlr"]]
        )
    finally:
        client.close()
    assert report["items"][0]["validations"]["correctness"]["is_correct"] is None
    assert all(url != destination for url in requests)


def test_page_spanning_pdf_annotation_is_not_a_direct_locator():
    from bib_lint.pdf_evidence import retrieval_entry, uncertain_uri_fields

    item = {
        "entry": {
            "key": "pdf-ref",
            "fields": {
                "title": "Actual Paper",
                "url": "https://arxiv.org/abs/2401.12345",
                "arxiv": "2401.12345",
            },
            "persons": {},
        },
        "pdf": {
            "fragments": [{"page": 1, "top": 100, "bottom": 110}],
            "uris": [{"page": 1, "top": 20, "bottom": 700}],
            "field_evidence": {"url": [{"uri": 0}], "arxiv": [{"uri": 0}]},
        },
    }
    assert uncertain_uri_fields(item) == {"url", "arxiv"}
    assert retrieval_entry(item)["fields"] == {"title": "Actual Paper"}
    assert item["entry"]["fields"]["url"]


def test_local_pdf_annotation_and_printed_locator_remain_usable():
    from bib_lint.pdf_evidence import uncertain_uri_fields

    item = {
        "pdf": {
            "fragments": [{"page": 1, "top": 100, "bottom": 110}],
            "uris": [{"page": 1, "top": 99, "bottom": 111}],
            "field_evidence": {"url": [{"uri": 0}], "doi": [{"fragment": 0}]},
        }
    }
    assert uncertain_uri_fields(item) == set()


def test_pdf_non_generational_suffix_is_extraction_uncertainty():
    from bib_lint.pdf_evidence import apply_extraction
    from bib_lint.verification.consensus import build_consensus
    from bib_lint.verification.matching import input_record, select_result

    item = {
        "entry": {
            "key": "pdf-ref",
            "fields": {"title": "An Example Paper", "year": "2024"},
            "persons": {"author": [{"first": ["Li"], "last": ["Huang"], "lineage": ["J."]}]},
        },
        "validations": {"extraction": {"state": "complete", "diagnostics": []}},
        "pdf": {"fragments": [], "field_evidence": {}, "uris": []},
    }
    original = input_record(item["entry"])
    found = {**original, "authors": [{"given": "Jie", "family": "Huang"}]}
    method = select_result("pmlr", original, [found], authority=True, lookup="url")
    result = apply_extraction(build_consensus([method]), item)
    assert result["is_correct"] is None
    assert any(f["code"] == "ambiguous_author_grouping" for f in result["input_findings"])


@pytest.mark.parametrize(
    "retrieval",
    [
        None,
        "wrong",
        {"next": -1, "resolved": False},
        {"next": True, "resolved": False},
        {"next": 0, "resolved": "yes"},
        {"next": 0, "resolved": False, "redirects": {"doi": 42}},
    ],
)
def test_malformed_saved_retrieval_state_fails_before_resume(tmp_path, retrieval):
    bib = source(tmp_path)
    client = MetadataClient(
        tmp_path / "cache",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=metadata())),
    )
    try:
        workspace, report, _ = run_audit(bib, output=tmp_path / "audit", client=client)
        report["items"][0]["validations"]["correctness"]["retrieval"] = retrieval
        workspace.final.write_text(json.dumps(report))
        before = workspace.final.read_bytes()
        with pytest.raises(ValueError, match="retrieval"):
            run_audit(bib, output=workspace.root, client=client)
        assert workspace.final.read_bytes() == before
    finally:
        client.close()
