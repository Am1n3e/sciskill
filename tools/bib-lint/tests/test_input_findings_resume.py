"""Local contradictions survive unavailable sources, checkpoints, and policy upgrades."""

import json
from contextlib import closing

import httpx
import pytest
from metadata_support import entry, html_record, write_bib
from provider_support import FixtureProvider
from support import ENTRY, FakeClient

from bib_lint.audit import audit_summary, run_audit
from bib_lint.scope import validate_report
from bib_lint.status import reference_status
from bib_lint.storage import write_json
from bib_lint.verification import verify_reference
from bib_lint.verification.http import LookupFailure, MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.viewer.data import load_report
from bib_lint.viewer.presentation import reference_detail

VENUE_KEY = "adv_consensus_shadowed_booktitle"


def unavailable(*_):
    raise LookupFailure("network_error", "Controlled source outage")


def isolated_bibliography(tmp_path, key=VENUE_KEY):
    return write_bib(tmp_path / "references.bib", key)


def has_finding(result, code):
    return any(check["code"] == code for check in result["input_findings"])


@pytest.mark.parametrize(
    "key,code",
    [
        (VENUE_KEY, "conflicting_venues"),
        ("adv_provider_split_arxiv_url", "conflicting_identifiers"),
    ],
)
def test_local_contradictions_are_visible_when_every_source_fails(key, code):
    result = verify_reference(
        entry(key),
        FakeClient(),
        methods=[FixtureProvider("offline_source", lookup=unavailable)],
    )
    assert has_finding(result, code)
    assert result["is_correct"] is None and result["canonical_ref"] is None
    assert reference_status({"correctness": result}) == "Needs review"
    assert result["consensus"]["records_found"] == 0
    assert result["consensus"]["unavailable"] == 1
    assert [m["status"] for m in result["methods"]] == ["error"]
    assert result["methods"][0]["error"]["code"] == "network_error"
    assert not result["methods"][0].get("found_ref")


def test_completed_audit_presents_local_conflicts_without_primary_evidence(tmp_path):
    source = isolated_bibliography(tmp_path)
    before = source.read_bytes()
    workspace, report, _ = run_audit(
        source,
        output=tmp_path / "audit",
        client=FakeClient(),
        methods=[FixtureProvider("offline_source", lookup=unavailable)],
    )
    assert report["verification_run"]["complete"]
    saved = json.loads(workspace.final.read_text())
    item = saved["items"][0]
    assert has_finding(item["validations"]["correctness"], "conflicting_venues")
    summary = audit_summary(saved)
    assert summary["needs_review"] == summary["completed"] == summary["source_failures"] == 1
    assert summary["invalid"] == summary["unresolved"] == 0
    rows = reference_detail(item)["comparisons"]
    assert any(row["Field"] == "venue" and row["Status"] == "Insufficient data" for row in rows)
    assert source.read_bytes() == before


def test_partial_checkpoint_retains_local_checks_and_resume_keeps_source_failures(tmp_path):
    source = isolated_bibliography(tmp_path)
    output = tmp_path / "audit"
    first = FixtureProvider("offline_a", lookup=unavailable)

    def interrupt(*_):
        raise KeyboardInterrupt

    second = FixtureProvider("offline_b", lookup=interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_audit(source, output=output, client=FakeClient(), methods=[first, second])
    checkpoint = output / "report.tmp.json"
    partial = json.loads(checkpoint.read_text())
    item = partial["items"][0]
    assert has_finding(item["validations"]["correctness"], "conflicting_venues")
    assert reference_status(item["validations"]) == "Pending"
    assert not (output / "report.json").exists()
    first.retrieval = lambda *_: pytest.fail("Saved source failure was unnecessarily retried")
    second.retrieval = unavailable
    _, resumed, _ = run_audit(source, output=output, client=FakeClient(), methods=[first, second])
    final = resumed["items"][0]
    assert reference_status(final["validations"]) == "Needs review"
    assert has_finding(final["validations"]["correctness"], "conflicting_venues")
    assert [m["status"] for m in final["validations"]["correctness"]["methods"]] == [
        "error",
        "error",
    ]


@pytest.mark.parametrize(
    "legacy_run",
    [
        {"policy_version": 5},
        {"policy_version": 6},
        {"policy_version": 7},
        {"orchestration_version": 3},
    ],
)
def test_old_saved_verdict_recomputes_input_checks_without_rewriting_evidence(tmp_path, legacy_run):
    source = isolated_bibliography(tmp_path)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert str(request.url) == "https://aclanthology.org/2025.emnlp-main.58/"
        return httpx.Response(200, text=html_record("datawise"))

    client = MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    try:
        workspace, first, _ = run_audit(
            source, output=tmp_path / "audit", client=client, methods=[METHODS["acl_anthology"]]
        )
        manifest = json.loads((workspace.cache / "checksum.json").read_text())
        raw = {
            row["path"]: (workspace.cache / row["path"]).read_bytes() for row in manifest["files"]
        }
        legacy = first["items"][0]["validations"]["correctness"]
        legacy.update(
            is_correct=True, policy_version=legacy_run.get("policy_version", 5), input_findings=[]
        )
        for method in legacy["methods"]:
            for comparison in method.get("comparisons", []):
                if comparison["field"] == "venue":
                    comparison["result"] = "match"
                    comparison.pop("input_findings", None)
            method["differences"] = []
        first["verification_run"].update(legacy_run)
        write_json(workspace.final, first)
        _, resumed, _ = run_audit(
            source, output=tmp_path / "audit", client=client, methods=[METHODS["acl_anthology"]]
        )
    finally:
        client.close()
    result = resumed["items"][0]["validations"]["correctness"]
    assert result["policy_version"] == resumed["verification_run"]["policy_version"] == 8
    assert resumed["verification_run"]["orchestration_version"] == 6
    assert reference_status({"correctness": result}) == "Needs review"
    assert has_finding(result, "conflicting_venues")
    assert len(calls) == 1
    assert result["methods"][0]["requests"][0]["cached"]
    assert all((workspace.cache / path).read_bytes() == value for path, value in raw.items())


@pytest.mark.parametrize(
    "malformed",
    [
        "not-a-list",
        None,
        [None],
        [{"field": "venue", "input": {}, "result": "unknown", "code": 7, "message": "bad"}],
        [{"field": "venue", "result": [], "code": "conflicting_venues", "message": "bad"}],
        [{"field": "venue", "result": {}, "code": "conflicting_venues", "message": "bad"}],
        [
            {
                "field": "venue",
                "input": {},
                "result": "invented",
                "code": "conflicting_venues",
                "message": "bad",
            }
        ],
    ],
)
def test_malformed_saved_input_findings_are_rejected_before_viewing_or_resuming(
    tmp_path, malformed
):
    source = isolated_bibliography(tmp_path)
    provider = FixtureProvider("offline_source", lookup=unavailable)
    workspace, report, _ = run_audit(
        source, output=tmp_path / "audit", client=FakeClient(), methods=[provider]
    )
    report["items"][0]["validations"]["correctness"]["input_findings"] = malformed
    write_json(workspace.final, report)
    before = workspace.final.read_bytes()
    with pytest.raises(ValueError, match="(?i)input findings"):
        validate_report(report)
    with pytest.raises(ValueError, match="(?i)input findings"):
        load_report(workspace.final)
    with pytest.raises(ValueError, match="(?i)input findings"):
        run_audit(source, output=workspace.root, client=FakeClient(), methods=[provider])
    assert workspace.final.read_bytes() == before
    assert not workspace.checkpoint.exists()


def test_policy_upgrade_rechecks_url_using_cached_source_evidence(tmp_path):
    source = tmp_path / "references.bib"
    source.write_text(
        "@article{Example,title={An Example Paper},author={Jane Smith},year={2025},"
        "journal={Example Journal},doi={10.1234/example},"
        "url={https://arxiv. org/abs/2501.12345}}"
    )
    payload = {
        "heading": ENTRY["fields"]["title"],
        "date": "2025",
        "journal": "Example Journal",
        "people": [{"given": "Jane", "family": "Smith"}],
        "ids": {"doi": "10.1234/example"},
    }
    calls = []

    def lookup(query, context):
        context.get("https://fixture.test/paper")
        return FixtureProvider(payload=payload).lookup(query, context)

    def respond(request):
        calls.append(request)
        return httpx.Response(200, text="Independent source evidence")

    provider = FixtureProvider(lookup=lookup)
    with closing(
        MetadataClient(tmp_path / "audit/cache", transport=httpx.MockTransport(respond))
    ) as client:
        workspace, first, _ = run_audit(
            source, output=tmp_path / "audit", client=client, methods=[provider]
        )
        manifest = (workspace.cache / "checksum.json").read_bytes()
        evidence = {
            row["path"]: (workspace.cache / row["path"]).read_bytes()
            for row in json.loads(manifest)["files"]
        }
        # Model the old policy's false positive, retaining its valid source outcome.
        first["verification_run"]["policy_version"] = 7
        legacy = first["items"][0]["validations"]["correctness"]
        legacy.update(is_correct=True, policy_version=7, input_findings=[])
        write_json(workspace.final, first)
        _, resumed, _ = run_audit(source, output=workspace.root, client=client, methods=[provider])
    result = resumed["items"][0]["validations"]["correctness"]
    assert result["policy_version"] == 8
    assert reference_status({"correctness": result}) == "Needs review"
    assert has_finding(result, "invalid_url")
    assert result["methods"][0]["requests"][0]["cached"]
    assert len(calls) == 1
    assert (workspace.cache / "checksum.json").read_bytes() == manifest
    assert all((workspace.cache / path).read_bytes() == value for path, value in evidence.items())
