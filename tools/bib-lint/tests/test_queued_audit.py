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
