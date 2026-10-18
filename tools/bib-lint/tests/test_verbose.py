import json

import httpx
import pytest

from bib_lint.verification.http import LookupFailure, MetadataClient


def events(messages):
    return [
        json.loads(m.removeprefix("Response:\n")) for m in messages if m.startswith("Response:\n")
    ]


def test_verbose_prints_error_success_and_cached_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)
    responses = iter(
        [
            httpx.Response(503, json={"error": "try later"}),
            httpx.Response(200, json={"papers": [{"title": "Example", "value": 123}]}),
        ]
    )
    client = MetadataClient(
        tmp_path, verbose=True, transport=httpx.MockTransport(lambda _: next(responses))
    )
    messages = []
    client.progress = messages.append
    url = "https://api.crossref.org/works"
    client.get(url)
    client.get(url)
    output = events(messages)
    assert [e["status_code"] for e in output] == [503, 200, 200]
    assert [e["cached"] for e in output] == [False, False, True]
    assert output[0]["body"] == {"error": "try later"}
    assert (
        output[1]["body"] == output[2]["body"] == {"papers": [{"title": "Example", "value": 123}]}
    )
    assert '\n  "url"' in messages[0]
    client.close()


@pytest.mark.parametrize(
    "tag, content_type", [("html", "text/html"), ("feed", "application/atom+xml")]
)
def test_verbose_keeps_full_non_json_body_and_redacts_secrets(tmp_path, tag, content_type):
    body = f"<{tag}>SECRET\n" + "x" * 2000 + f"</{tag}>"
    client = MetadataClient(
        tmp_path,
        verbose=True,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                406,
                text=body,
                headers={"Set-Cookie": "session=private", "Content-Type": content_type},
            )
        ),
    )
    messages = []
    client.progress = messages.append
    with pytest.raises(LookupFailure):
        client.get("https://export.arxiv.org/api/query", headers={"x-api-key": "SECRET"})
    assert events(messages) == []
    assert messages[0].endswith(body.replace("SECRET", "[redacted]"))
    assert "set-cookie: [redacted]" in messages[0]
    assert "SECRET" not in "\n".join(messages)
    client.close()


def test_verbose_network_error_has_no_fake_response(tmp_path, monkeypatch):
    monkeypatch.setattr("bib_lint.verification.http.time.sleep", lambda _: None)

    def fail(request):
        raise httpx.ConnectError("Connection refused", request=request)

    client = MetadataClient(tmp_path, verbose=True, transport=httpx.MockTransport(fail))
    messages = []
    client.progress = messages.append
    with pytest.raises(LookupFailure):
        client.get("https://api.crossref.org/works")
    output = events(messages)
    assert len(output) == 3
    assert output[0]["status_code"] is None
    assert output[0]["error"]["message"] == "Connection refused"
    client.close()


def test_default_does_not_dump_responses(tmp_path):
    client = MetadataClient(
        tmp_path, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True}))
    )
    messages = []
    client.progress = messages.append
    client.get("https://api.crossref.org/works")
    assert events(messages) == []
    client.close()
