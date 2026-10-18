import hashlib
import json
from pathlib import Path

import httpx
import pytest

from bib_lint.verification.http import LookupFailure, MetadataClient


def make_client(tmp_path, respond):
    client = MetadataClient(tmp_path, transport=httpx.MockTransport(respond))
    client.citation_key = "lambert2024tulu"
    client.method = "arxiv"
    return client


@pytest.mark.parametrize(
    "extension, content_type, raw",
    [
        ("json", "application/json", b'{ "value" : 1, "items": [2,3] }\r\n'),
        ("xml", "application/atom+xml", b'<?xml version="1.0"?>\n<feed>  original </feed>\n'),
        ("html", "text/html", b"<!DOCTYPE html>\r\n<html> original </html>"),
    ],
)
def test_raw_body_and_manifest(tmp_path, extension, content_type, raw):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=raw, headers={"Content-Type": content_type})

    client = make_client(tmp_path, respond)
    first = client.get("https://example.org/record")
    manifest = json.loads((tmp_path / "checksum.json").read_text())
    entry = manifest["files"][0]
    path = tmp_path / entry["path"]
    assert path.parent.name == "lambert2024tulu"
    assert path.name.startswith("arxiv_") and path.suffix == "." + extension
    assert path.read_bytes() == raw
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert client.get("https://example.org/record") == first
    assert len(calls) == 1
    client.close()


@pytest.mark.parametrize(
    "damage",
    ["changed_body", "missing_checksum", "missing_file", "bad_manifest", "missing_manifest"],
)
def test_damaged_cache_is_removed_and_refetched(tmp_path, monkeypatch, damage):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=b'{"original":true}')

    client = make_client(tmp_path, respond)
    client.get("https://example.org/record")
    manifest_path = tmp_path / "checksum.json"
    manifest = json.loads(manifest_path.read_text())
    old_file = tmp_path / manifest["files"][0]["path"]
    if damage == "changed_body":
        old_file.write_text('{"tampered":true}')
    elif damage == "missing_checksum":
        del manifest["files"][0]["sha256"]
        manifest_path.write_text(json.dumps(manifest))
    elif damage == "missing_file":
        old_file.unlink()
    elif damage == "bad_manifest":
        manifest_path.write_text("not JSON")
    else:
        manifest_path.unlink()
    assert client.get("https://example.org/record") == '{"original":true}'
    assert len(calls) == 2
    assert not old_file.exists()
    replacement = json.loads(manifest_path.read_text())["files"][0]
    raw = (tmp_path / replacement["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == replacement["sha256"]
    client.close()


def test_error_responses_archived_but_not_reused(tmp_path, monkeypatch):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            406, content=b"<html>Not acceptable</html>", headers={"Content-Type": "text/html"}
        )

    client = make_client(tmp_path, respond)
    for _ in range(2):
        with pytest.raises(LookupFailure):
            client.get("https://example.org/record")
    assert len(calls) == 2
    entries = json.loads((tmp_path / "checksum.json").read_text())["files"]
    assert len(entries) == 2
    assert all(e["status_code"] == 406 and e["path"].endswith(".html") for e in entries)
    client.close()


def test_unsafe_citation_keys_and_request_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    client = make_client(tmp_path, lambda r: httpx.Response(200, json={"url": str(r.url)}))
    client.citation_key = "../different/place"
    for suffix in ["first", "second"]:
        assert suffix in client.get("https://example.org/" + suffix)
    assert "first" in client.get("https://example.org/first")
    entries = json.loads((tmp_path / "checksum.json").read_text())["files"]
    assert len(entries) == 2
    assert all(len(Path(e["path"]).parts) == 2 for e in entries)
    assert client.evidence[-1]["cached"] is True
    client.close()
