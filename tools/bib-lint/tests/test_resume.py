import json

import httpx
import pytest
from provider_support import fixture_registry
from support import ENTRY, RECORD, FakeClient

from bib_lint.storage import report_lock
from bib_lint.verification import verify_file
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.matching import select_result
from bib_lint.workflow import parse_bib


def report_file(tmp_path, used=True):
    path = tmp_path / "references.tmp.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "summary": {},
                "items": [
                    {"entry": ENTRY, "validations": {"is_used": used}},
                ],
            }
        )
    )
    return path


def result(name):
    return select_result(name, RECORD, [RECORD], authority=True)


def test_interrupt_checkpoints_each_method_and_resumes(tmp_path):
    source = report_file(tmp_path)
    final = tmp_path / "references.json"
    final.write_text("previous final")
    calls = []

    def first(record, client):
        calls.append("first")
        return result("first")

    def second(record, client):
        saved = json.loads(source.read_text())
        assert saved["items"][0]["validations"]["correctness"]["methods"][0]["name"] == "first"
        assert final.read_text() == "previous final"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        verify_file(
            source,
            client=FakeClient(),
            methods=fixture_registry({"first": first, "second": second}),
        )
    assert source.exists()
    assert not json.loads(source.read_text())["verification_run"]["complete"]
    logs = []
    output, _ = verify_file(
        source,
        client=FakeClient(),
        progress=logs.append,
        methods=fixture_registry({"first": first, "second": lambda r, c: result("second")}),
    )
    assert calls == ["first"]
    assert output == final and not source.exists()
    assert json.loads(final.read_text())["verification_run"]["complete"]
    assert "  first: Resumed (Found)" in logs
    assert "  second: Fetching ..." in logs
    assert "  found: 2/2" in logs
    assert "  consensus: 2/2" in logs
    # Re-running the exact command after completion reuses the final report.
    verify_file(
        source,
        client=FakeClient(),
        methods=fixture_registry({"first": first, "second": lambda r, c: result("second")}),
    )
    assert calls == ["first"]


def test_unused_entries_never_call_providers(tmp_path):
    source = report_file(tmp_path, used=False)

    def forbidden(record, client):
        pytest.fail("Unused reference reached provider")

    output, summary = verify_file(
        source, client=FakeClient(), methods=fixture_registry({"test": forbidden})
    )
    assert summary["skipped_unused"] == 1
    assert "correctness" not in json.loads(output.read_text())["items"][0]["validations"]


def test_missing_usage_fails_before_network(tmp_path):
    source = report_file(tmp_path, used=None)
    with pytest.raises(ValueError, match="--aux"):
        verify_file(source, client=FakeClient())


def test_concurrent_writer_rejected(tmp_path):
    source = report_file(tmp_path)
    with report_lock(tmp_path / "references.json"):
        with pytest.raises(ValueError, match="already in use"):
            verify_file(source, client=FakeClient())
    assert source.exists()


def test_parse_protects_resume_checkpoint(tmp_path):
    source = report_file(tmp_path)
    data = json.loads(source.read_text())
    data["verification_run"] = {"complete": False}
    source.write_text(json.dumps(data))
    bib = tmp_path / "references.bib"
    bib.write_text("@book{A,title={A}}")
    first, _ = parse_bib(bib)
    assert "resume" in first.error
    assert json.loads(source.read_text()) == data


def test_changed_source_rejects_stale_checkpoint(tmp_path):
    source = report_file(tmp_path)
    other = tmp_path / "input.json"
    data = json.loads(source.read_text())
    data["items"][0]["entry"]["fields"]["year"] = "1990"
    other.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="different inputs"):
        verify_file(other, output=tmp_path / "references.json", client=FakeClient())


def test_errors_preserved_on_resume_and_retried_on_refresh(tmp_path):
    source = report_file(tmp_path)

    def failure(r, c):
        raise ValueError("failed provider")

    _, summary = verify_file(
        source,
        client=FakeClient(),
        methods=fixture_registry({"first": lambda r, c: result("first"), "second": failure}),
    )
    assert summary["method_errors"] == 1

    def forbidden(r, c):
        pytest.fail("Completed method rerun")

    _, summary = verify_file(
        source,
        client=FakeClient(),
        methods=fixture_registry({"first": forbidden, "second": forbidden}),
    )
    assert summary["method_errors"] == 1
    _, summary = verify_file(
        source,
        refresh=True,
        client=FakeClient(),
        methods=fixture_registry(
            {"first": lambda r, c: result("first"), "second": lambda r, c: result("second")}
        ),
    )
    assert summary["method_errors"] == 0


def test_retry_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, text="OK")]
    )
    client = MetadataClient(tmp_path, transport=httpx.MockTransport(lambda _: next(responses)))
    messages = []
    client.progress = messages.append
    assert client.get("https://api.crossref.org/test") == "OK"
    assert "Rate limit backoff 3 seconds" in messages
    assert client.evidence[0]["attempts"] == 2
    client.close()


@pytest.mark.parametrize("failure", ["rate_limit", "server_error", "network"])
def test_configured_backoff_schedule(tmp_path, monkeypatch, failure):
    clock = [100.0]
    sleeps = []
    monkeypatch.setattr("bib_lint.verification.http.time.monotonic", lambda: clock[0])

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("bib_lint.verification.http.time.sleep", sleep)
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 3:
            return httpx.Response(200, text="OK")
        if failure == "network":
            raise httpx.ConnectError("Temporary failure", request=request)
        return httpx.Response(
            429 if failure == "rate_limit" else 503,
            headers={"Retry-After": str((2, 4)[len(calls) - 1])},
        )

    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    assert client.get("https://fixture.test/paper") == "OK"
    assert sleeps == [2, 4]
    assert client.evidence[0]["attempts"] == 3
    client.close()


def test_configured_retries_stop_after_budget(tmp_path, monkeypatch):
    from bib_lint.verification.http import LookupFailure

    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    client = MetadataClient(tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    with pytest.raises(LookupFailure, match="rate limit"):
        client.get("https://fixture.test/paper")
    assert client.evidence[0]["attempts"] == 3
    client.close()


def test_verify_single_key_preserves_other_results_and_pending_state(tmp_path):
    source = report_file(tmp_path)
    report = json.loads(source.read_text())
    other = json.loads(json.dumps(report["items"][0]))
    other["entry"]["key"] = "Other"
    report["items"].append(other)
    source.write_text(json.dumps(report))
    calls = []

    def verify(record, client):
        calls.append(True)
        return result("test")

    output, _ = verify_file(
        source,
        citation_key="example",
        client=FakeClient(),
        methods=fixture_registry({"test": verify}),
    )
    assert output == source
    assert len(calls) == 1
    partial = json.loads(source.read_text())
    assert not partial["verification_run"]["complete"]
    assert "correctness" not in partial["items"][1]["validations"]
    first = partial["items"][0]["validations"]["correctness"]
    final, _ = verify_file(
        source,
        citation_key="Other",
        refresh=True,
        client=FakeClient(),
        methods=fixture_registry({"test": verify}),
    )
    assert final.name == "references.json"
    assert not source.exists()
    assert len(calls) == 2
    assert json.loads(final.read_text())["items"][0]["validations"]["correctness"] == first


@pytest.mark.parametrize("key, used", [("missing", True), ("Example", False)])
def test_invalid_or_unused_key_does_not_modify_checkpoint(tmp_path, key, used):
    source = report_file(tmp_path, used=used)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="Citation key"):
        verify_file(source, citation_key=key, client=FakeClient())
    assert source.read_bytes() == original
