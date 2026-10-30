"""Independent challenge expectations are required regression checks."""

import hashlib
import json
import re
from dataclasses import asdict

import pytest
from defusedxml import ElementTree

from bib_lint.audit import prepare_input
from bib_lint.parser import parse_file
from bib_lint.verification.consensus import build_consensus
from bib_lint.verification.matching import input_record, select_result
from bib_lint.verification.providers import METHODS
from bib_lint.verification.providers.common import citation_candidate
from evaluation.adversarial import (
    ATOM,
    BIBLIOGRAPHY,
    CASES,
    SOURCES,
    FixedPaperWorld,
    check_case,
    citation_html,
    run_challenge,
)


@pytest.fixture(scope="module")
def challenge(tmp_path_factory):
    return run_challenge(tmp_path_factory.mktemp("adversarial"))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["citation_key"])
def test_adversarial_independent_expectations(case, challenge):
    observed = next(c for c in challenge["cases"] if c["citation_key"] == case["citation_key"])
    assert observed["passes"], observed["failures"]
    assert observed["combined"]["passes"], observed["combined"]["failures"]


@pytest.mark.parametrize(
    "key,probe",
    [
        pytest.param(
            "adv_consensus_ſb3",
            "exact_key_selection",
            id="unicode-long-s-key",
        ),
        pytest.param(
            "adv_consensus_sb3",
            "exact_key_selection",
            id="unicode-ascii-key",
        ),
        pytest.param(
            "adv_flow_ſingle",
            "aux_casefold_usage",
            id="unicode-aux-silent-skip",
        ),
        ("adv_flow_CodeNav/../%2E%2E", "literal_key_and_cache_containment"),
        ("adv_flow_<script>alert(1)</script>", "literal_key_and_cache_containment"),
    ],
)
def test_adversarial_workflow_invariants(key, probe, challenge):
    observed = next(
        p for p in challenge["workflow_probes"] if p["citation_key"] == key and p["probe"] == probe
    )
    assert observed["passes"], observed["observed"]


def test_authored_mutations_survive_combination():
    text = BIBLIOGRAPHY.read_text()
    sections = re.split(r"(?m)^% CASE [^\n]+\n", text)[1:]
    assert len(sections) == len(CASES) == 35
    parsed = parse_file(BIBLIOGRAPHY)
    assert list(parsed.entries) == [c["citation_key"] for c in CASES]
    assert {c["designer"] for c in CASES} == {"matching", "providers", "consensus", "parent"}
    for case, raw in zip(CASES, sections, strict=True):
        assert hashlib.sha256(raw.strip().encode()).hexdigest() == case["raw_entry_sha256"]
    report, _, _ = prepare_input(BIBLIOGRAPHY)
    assert report["verification_scope"]["eligible_keys"] == list(parsed.entries)


@pytest.mark.parametrize("name", list(SOURCES["records"]))
def test_replay_preserves_independent_source_facts(name):
    world = FixedPaperWorld()
    source = SOURCES["records"][name]
    record, provider = source["record"], source["provider"]
    if provider == "arxiv":
        entries = ElementTree.fromstring(world.excerpt(source["source"])).findall(ATOM + "entry")
        actual = next(METHODS[provider]._records(entries)).as_record()
    elif provider == "openreview":
        note = json.loads(world.excerpt(source["source"]))
        actual = next(METHODS[provider]._records([note])).as_record()
    else:
        actual = citation_candidate(
            citation_html(record), source["source"], METHODS[provider].identifiers(source["source"])
        ).as_record()
    for field in ("title", "authors", "year", "venue", "record_type", "publication_status"):
        assert actual[field] == record[field], field
    for identifier in ("doi", "arxiv"):
        assert actual["identifiers"].get(identifier) == record["identifiers"].get(identifier)


def test_conflict_check_requires_actual_primary_evidence():
    """Generic review from one preprint cannot masquerade as a three-source conflict."""
    case = next(c for c in CASES if c["citation_key"] == "adv_consensus_kim_unlinked_primaries")
    # Rebuild the real arXiv method from the independently fixed record and original input.
    entry = asdict(parse_file(BIBLIOGRAPHY).entries[case["citation_key"]])
    record = next(
        s["record"]
        for s in SOURCES["records"].values()
        if s["provider"] == "arxiv" and s["record"]["identifiers"]["arxiv"] == "2303.17491v3"
    )
    method = select_result("arxiv", input_record(entry), [record], authority=True)
    item = {"entry": entry, "validations": {"correctness": build_consensus([method])}}
    observed = check_case(case, item)
    assert not observed["passes"]
    assert any("Required neurips" in f for f in observed["failures"])
    assert any("Required openreview" in f for f in observed["failures"])


def test_runner_scores_both_audits_and_preserves_input(challenge):
    assert challenge["combined_audit"]["completed"] == len(CASES)
    assert challenge["combined_audit"]["pending"] == 0
    assert all("combined" in c and "passes" in c["combined"] for c in challenge["cases"])
    for report in challenge["cases"]:
        case = next(c for c in CASES if c["citation_key"] == report["citation_key"])
        assert case["acceptable_statuses"]  # Desired behavior remains separate from observations.
    test_authored_mutations_survive_combination()
