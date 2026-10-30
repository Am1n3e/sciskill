"""Offline challenge: real adapters over fixed public-paper facts, never a live search.

Run from tools/bib-lint: python -m evaluation.adversarial --output DIRECTORY
The command exits nonzero for missed expectations; audit completion is separate.
"""

import argparse
import hashlib
import html
import json
import re
import time
import unicodedata
from collections import Counter
from contextlib import contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx

from bib_lint.audit import audit_summary, prepare_input, run_audit
from bib_lint.scope import selected_items, validate_report
from bib_lint.status import reference_status
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from bib_lint.viewer.data import read_response, suggestions
from bib_lint.viewer.presentation import reference_detail

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures/e2e"
BIBLIOGRAPHY = FIXTURES / "adversarial.bib"
CASES = json.loads((FIXTURES / "adversarial.cases.json").read_text())["cases"]
SOURCES = json.loads((FIXTURES / "adversarial.sources.json").read_text())
ATOM = "{http://www.w3.org/2005/Atom}"


def search_text(value):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def search_matches(query, title):
    """Controlled search over fixed titles, independent of bib-lint's matcher."""
    return SequenceMatcher(None, search_text(query), search_text(title)).ratio() >= 0.7


def citation_html(record):
    values = [("citation_title", record["title"])]
    values.extend(
        ("citation_author", " ".join(a.get(k, "") for k in ("given", "family", "suffix")))
        for a in record["authors"]
    )
    values.extend(
        [
            ("citation_publication_date", record["year"]),
            ("citation_conference_title", record["venue"]),
        ]
    )
    if record["identifiers"].get("doi"):
        values.append(("citation_doi", record["identifiers"]["doi"]))
    tags = "".join(
        f'<meta name="{key}" content="{html.escape(str(value), quote=True)}">'
        for key, value in values
        if value
    )
    return "<html><head>" + tags + "</head></html>"


class FixedPaperWorld:
    """Address records by URL/ID; never substitute the current case's base paper."""

    def __init__(self):
        self.records = list(SOURCES["records"].values())
        self.requests = []
        self.unexpected = []
        addresses = [
            (urlsplit(s["source"]).hostname, urlsplit(s["source"]).path.rstrip("/"))
            for s in self.records
            if s["provider"] not in {"arxiv", "openreview"}
        ]
        assert len(addresses) == len(set(addresses)), "Ambiguous path-only replay records"

    def excerpt(self, source):
        data = SOURCES["excerpts"][source]
        raw = (FIXTURES / data["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == data["excerpt_sha256"]
        return raw

    def atom(self, request):
        query = request.url.params
        records = [r["record"] for r in self.records if r["provider"] == "arxiv"]
        if query.get("id_list"):
            identifier = query["id_list"]
            records = [
                r
                for r in records
                if r["identifiers"]["arxiv"] == identifier
                or re.sub(r"v\d+$", "", r["identifiers"]["arxiv"]) == identifier
            ]
        else:
            term = query.get("search_query", "").removeprefix('ti:"').removesuffix('"')
            records = [r for r in records if search_matches(term, r["title"])]
        feed = ET.Element(ATOM + "feed")
        for record in records:
            original = ET.fromstring(self.excerpt(record["url"]))
            feed.extend(original.findall(ATOM + "entry"))
        return ET.tostring(feed, encoding="unicode")

    def notes(self, request):
        notes = [
            json.loads(self.excerpt(r["source"]))
            for r in self.records
            if r["provider"] == "openreview"
        ]
        query = request.url.params
        if query.get("id"):
            notes = [n for n in notes if n["id"] == query["id"]]
        elif query.get("content.venueid"):
            notes = [
                n
                for n in notes
                if n["content"].get("venueid", {}).get("value") == query["content.venueid"]
            ]
        else:
            notes = [
                n
                for n in notes
                if search_matches(query.get("term", ""), n["content"]["title"]["value"])
            ]
        return json.dumps({"notes": notes, "count": len(notes)}, ensure_ascii=False)

    def catalogs(self):
        records = SOURCES["records"]
        datawise = records["datawise"]["record"]
        neurips = records["kim_neurips"]["record"]
        sb3 = records["sb3"]["record"]
        return {
            "proceedings.mlr.press/": '<li><a href="v37">Volume 37</a> ICML 2015</li>',
            "proceedings.mlr.press/v37": (
                FIXTURES.parent / "providers/pmlr-volume.html"
            ).read_text(),
            "jmlr.org/papers": '<li><a href="v22/">Volume 22</a> January 2021</li>',
            "jmlr.org/papers/v22": (
                f"<dl><dt>{html.escape(sb3['title'])}</dt>"
                '<dd>[<a href="20-1364.html">abs</a>]</dd></dl>'
            ),
            "aclanthology.org/events": '<a href="/events/emnlp-2025/">EMNLP 2025</a>',
            "aclanthology.org/events/emnlp-2025": (
                '<a href="/volumes/2025.emnlp-main/">EMNLP 2025</a>'
            ),
            "aclanthology.org/volumes/2025.emnlp-main": (
                f'<a href="{datawise["url"]}">{html.escape(datawise["title"])}</a>'
            ),
            "proceedings.neurips.cc/": '<a href="/paper_files/paper/2023">2023</a>',
            "proceedings.neurips.cc/paper_files/paper/2023": (
                f'<a href="{neurips["url"]}">{html.escape(neurips["title"])}</a>'
            ),
        }

    def __call__(self, request):
        self.requests.append(str(request.url))
        host, path = request.url.host, request.url.path
        if host == "export.arxiv.org" and path == "/api/query":
            return httpx.Response(
                200, text=self.atom(request), headers={"content-type": "text/xml"}
            )
        if host in {"api.openreview.net", "api2.openreview.net"} and path in {
            "/notes",
            "/notes/search",
        }:
            return httpx.Response(200, text=self.notes(request))
        for source in self.records:
            url = urlsplit(source["source"])
            if (url.hostname, url.path.rstrip("/")) == (host, path.rstrip("/")):
                return httpx.Response(200, text=citation_html(source["record"]))
        address = host + (path.rstrip("/") or "/")
        catalogs = self.catalogs()
        if address in catalogs:
            return httpx.Response(200, text="<html>" + catalogs[address] + "</html>")
        if host in {
            "proceedings.mlr.press",
            "jmlr.org",
            "aclanthology.org",
            "proceedings.neurips.cc",
        }:
            return httpx.Response(404, text="Absent from the limited fixed-paper replay universe")
        self.unexpected.append(str(request.url))
        raise AssertionError(f"Unexpected replay request: {request.url}")


@contextmanager
def logical_clock():
    current = [100.0]
    clock = SimpleNamespace(
        monotonic=lambda: current[0],
        sleep=lambda seconds: current.__setitem__(0, current[0] + seconds),
        time=time.time,
    )
    with patch("bib_lint.verification.http.time", clock):
        yield


def replay(output, providers=None):
    world = FixedPaperWorld()
    with logical_clock():
        client = MetadataClient(output / "cache", transport=httpx.MockTransport(world))
        try:
            workspace, report, _ = run_audit(
                BIBLIOGRAPHY,
                output=output,
                client=client,
                methods=[METHODS[p] for p in providers] if providers else None,
            )
        finally:
            client.close()
    assert not world.unexpected
    assert report["verification_run"]["complete"]
    assert workspace.final.exists() and not workspace.checkpoint.exists()
    validate_report(report)
    return report


def check_fields(case, methods):
    failures = []
    for check in case["field_checks"]:
        name = check.get("source")
        selected = [
            m
            for m in methods
            if m.get("found_ref")
            and (not name or m["name"] == name or name == "all_authoritative_found")
            and (name != "all_authoritative_found" or m.get("authority"))
        ]
        results = [
            c["result"]
            for m in selected
            for c in m.get("comparisons", [])
            if c["field"] == check["field"]
        ]
        if not results or any(result not in check["results"] for result in results):
            failures.append(f"{name or 'selected sources'} {check['field']}: {results}")
    return failures


def check_case(case, item):
    result = item["validations"]["correctness"]
    status = reference_status(item["validations"])
    methods = [m for m in result["methods"] if m["name"] in case["providers"]]
    failures = []
    if status not in case["acceptable_statuses"]:
        failures.append(f"Expected {case['acceptable_statuses']}; observed {status}")
    failures.extend(check_fields(case, methods))
    failures.extend(check_sources(case, result))
    if case.get("required_finding") and not finding_present(case["required_finding"], methods):
        failures.append("The contradictory provider locator has no explicit finding")
    if case.get("viewer_checks") and any(s["Field"] == "year" for s in suggestions(item)):
        failures.append("Conflicting primary versions produced an unqualified correction")
    return {
        "citation_key": case["citation_key"],
        "status": status,
        "passes": not failures,
        "failures": failures,
        "is_control": case["is_control"],
        "scope_boundary": case["scope_boundary"],
        "expectation_class": case["expectation_class"],
        "regression_family": case["regression_family"],
        "sources": [
            {
                "name": m["name"],
                "status": m["status"],
                "comparisons": {c["field"]: c["result"] for c in m.get("comparisons", [])},
            }
            for m in methods
        ],
    }


def finding_present(expected, methods):
    return any(
        c["field"] in expected["fields"] and c["result"] in expected["results"]
        for m in methods
        for c in m.get("comparisons", [])
    ) or any(m.get("error", {}).get("code") in expected["error_codes"] for m in methods)


def check_sources(case, result):
    failures = []
    methods = {m["name"]: m for m in result["methods"]}
    for name, expected in case["required_sources"].items():
        source = methods.get(name, {})
        for field in ("status", "authority"):
            if source.get(field) != expected[field]:
                failures.append(f"Required {name} {field}: {expected[field]}")
        if len(source.get("candidates", [])) < expected.get("min_candidates", 0):
            failures.append(f"Required {name} candidate evidence is missing")
    if "consensus_checks" in case:
        actual = (result.get("canonical_ref") or {}).get("url")
        if actual != case["consensus_checks"]["canonical_source"]:
            failures.append(f"Unexpected canonical source: {actual}")
    return failures


def workflow_probes(report, audit_path):
    probes = []
    for case in [c for c in CASES if c.get("selection_scenario")]:
        key = case["citation_key"]
        try:
            observed = [i["entry"]["key"] for i in selected_items(report, key)]
            passes = observed == [key]
        except ValueError as exc:
            observed, passes = str(exc), False
        probes.append(
            {
                "citation_key": key,
                "probe": "exact_key_selection",
                "passes": passes,
                "observed": observed,
            }
        )
    aux_report, _, warnings = prepare_input(BIBLIOGRAPHY, aux=FIXTURES / "adversarial-alias.aux")
    expected = "adv_flow_ſingle"
    probes.append(
        {
            "citation_key": expected,
            "probe": "aux_casefold_usage",
            "passes": expected in aux_report["verification_scope"]["eligible_keys"],
            "observed": {
                "eligible_keys": aux_report["verification_scope"]["eligible_keys"],
                "warnings": warnings,
            },
        }
    )
    probes.extend(hostile_key_probes(report, audit_path))
    return probes


def hostile_key_probes(report, audit_path):
    manifest = json.loads((audit_path / "cache/checksum.json").read_text())
    probes = []
    for key in ("adv_flow_CodeNav/../%2E%2E", "adv_flow_<script>alert(1)</script>"):
        entries = [e for e in manifest["files"] if e["citation_key"] == key]
        for entry in entries:
            read_response(audit_path / "cache", entry)  # Enforces path and checksum safety.
        item = next(i for i in report["items"] if i["entry"]["key"] == key)
        detail = reference_detail(item)
        probes.append(
            {
                "citation_key": key,
                "probe": "literal_key_and_cache_containment",
                "passes": bool(entries) and detail["entry"]["key"] == key,
                "observed": {
                    "literal_key": detail["entry"]["key"],
                    "cached_responses": len(entries),
                },
            }
        )
    return probes


def run_challenge(output):
    """Audit the single bibliography together, then isolate provider combinations."""
    output = Path(output).resolve()
    combined = replay(output / "combined")
    registries = sorted({tuple(c["providers"]) for c in CASES})
    focused = {names: replay(output / ("focus-" + "-".join(names)), names) for names in registries}
    observations = []
    for case in CASES:
        report = focused[tuple(case["providers"])]
        item = next(i for i in report["items"] if i["entry"]["key"] == case["citation_key"])
        observed = check_case(case, item)
        together = next(i for i in combined["items"] if i["entry"]["key"] == case["citation_key"])
        observed["combined"] = check_case(case, together)
        observations.append(observed)
    probes = workflow_probes(combined, output / "combined")
    result = {
        "mode": "offline_fixed_source_replay",
        "bibliography": str(BIBLIOGRAPHY),
        "combined_report_path": str(output / "combined/report.json"),
        "expectation_policy": "Independent expectations; failures are not accepted as correct.",
        "combined_audit": audit_summary(combined),
        "case_count": len(observations),
        "expectations_met": sum(c["passes"] for c in observations),
        "expectations_missed": sum(not c["passes"] for c in observations),
        "combined_expectations_met": sum(c["combined"]["passes"] for c in observations),
        "combined_expectations_missed": sum(not c["combined"]["passes"] for c in observations),
        "focused_statuses": dict(Counter(c["status"] for c in observations)),
        "workflow_probes": probes,
        "cases": observations,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "challenge-results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_challenge(args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, ensure_ascii=False))
    return (
        0
        if result["expectations_missed"] == 0
        and result["combined_expectations_missed"] == 0
        and all(p["passes"] for p in result["workflow_probes"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
