"""Canonical replay drives the real provider adapters without source mutations."""

from contextlib import closing

import httpx
import pytest
from pdf_e2e.build import FIXTURES, read_json

from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.context import RequestContext
from bib_lint.verification.providers.protocol import LookupQuery


@pytest.mark.parametrize(
    ("record_id", "provider"),
    [
        ("codenav", "arxiv"),
        ("datawise", "acl_anthology"),
        ("trial_acl", "acl_anthology"),
        ("sb3", "jmlr"),
        ("hcpi", "pmlr"),
        ("kim_neurips", "neurips"),
        ("pal_accepted", "openreview"),
    ],
)
def test_canonical_http_replay_runs_real_provider(tmp_path, record_id, provider):
    from pdf_e2e.replay import ScholarlyReplay

    truth = read_json(FIXTURES / "truth.json")
    record = truth["canonical_records"][record_id]["metadata"]
    replay = ScholarlyReplay(truth["canonical_records"])
    client = MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(replay))
    query = LookupQuery.from_entry(
        {
            "key": "input",
            "type": "misc",
            "fields": {"title": record["title"], "year": str(record["year"]), "url": record["url"]},
            "persons": {
                "author": [
                    {
                        "first": a.get("given", "").split(),
                        "middle": [],
                        "prelast": [],
                        "last": a.get("family", "").split(),
                        "lineage": [],
                        "kind": "person",
                    }
                    for a in record.get("authors", [])
                ]
            },
        }
    )
    adapter = METHODS[provider]
    result = adapter.lookup(query, RequestContext(client, adapter.descriptor, "input"))
    client.close()
    assert result.complete
    assert result.candidates
    assert result.candidates[0].title == record["title"]
    assert replay.unexpected == []


def test_replay_rejects_unknown_external_destinations():
    from pdf_e2e.replay import ScholarlyReplay

    replay = ScholarlyReplay({})
    with pytest.raises(AssertionError, match="Unexpected"):
        replay(httpx.Request("GET", "https://unrelated.example/paper"))
    assert replay.unexpected


def test_acl_replay_preserves_raw_display_alias_and_explicit_citation(tmp_path):
    from pdf_e2e.replay import ScholarlyReplay

    truth = read_json(FIXTURES / "truth.json")
    source = truth["canonical_records"]["trial_acl"]
    replay = ScholarlyReplay(truth["canonical_records"])
    response = replay(httpx.Request("GET", source["metadata"]["url"]))
    assert 'content="Sujian Li (李素建)"' in response.text
    assert 'id="citeBibtexContent"' in response.text
    assert "Li, Sujian" in response.text
    adapter = METHODS["acl_anthology"]
    query = LookupQuery.from_entry(
        {
            "key": "trial",
            "type": "inproceedings",
            "fields": {"title": source["metadata"]["title"], "url": source["metadata"]["url"]},
            "persons": {},
        }
    )
    with closing(
        MetadataClient(tmp_path / "cache", transport=httpx.MockTransport(replay))
    ) as client:
        result = adapter.lookup(query, RequestContext(client, adapter.descriptor, "trial"))
    author = result.candidates[0].authors[4]
    assert author.given == "Sujian" and author.family == "Li"
