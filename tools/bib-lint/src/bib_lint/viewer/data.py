"""Presentation data and integrity-checked, read-only cache access."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from defusedxml import minidom

from bib_lint.scope import validate_report
from bib_lint.status import field_status, reference_status
from bib_lint.verification.matching import compare_fields, input_record


def load_report(path):
    path = Path(path)
    if path.is_dir():
        checkpoint = path / "report.tmp.json"
        path = checkpoint if checkpoint.exists() else path / "report.json"
    if not path.exists() and path.name.endswith(".tmp.json"):
        path = path.with_name(path.name[:-9] + ".json")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("items"), list):
        raise ValueError("Choose a bib-lint report containing items.")
    for item in report["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("entry"), dict)
            or not isinstance(item.get("validations"), dict)
        ):
            raise ValueError("Report items must contain entry and validations objects.")
    if report.get("schema_version") in (3, 4):
        validate_report(report)
    return report


def correctness(item):
    return reference_status(item["validations"])


def record_urls(item):
    urls = []
    for method in item["validations"].get("correctness", {}).get("methods", []):
        records = ([method["found_ref"]] if method.get("found_ref") else []) + method.get(
            "candidates", []
        )
        candidates = [method.get("source_url")]
        for record in records:
            ids = record.get("identifiers", {})
            candidates.extend(
                [
                    record.get("url"),
                    "https://doi.org/" + ids["doi"] if ids.get("doi") else None,
                    "https://arxiv.org/abs/" + ids["arxiv"] if ids.get("arxiv") else None,
                ]
            )
        for url in candidates:
            if (
                isinstance(url, str)
                and urlsplit(url).scheme in {"http", "https"}
                and url not in urls
            ):
                urls.append(url)
    return urls


def note(item):
    result = item["validations"].get("correctness")
    used = item["validations"].get("is_used")
    if not result:
        return (
            "Not verified"
            if used
            else "Unused; not verified"
            if used is False
            else "Usage not checked"
        )
    if result.get("complete") is False:
        return "Verification in progress"
    differences = sorted(
        {d["field"] for m in result.get("methods", []) for d in m.get("differences", [])}
    )
    errors = [m["name"] for m in result.get("methods", []) if m.get("status") == "error"]
    parts = (
        ["Check " + ", ".join(differences)]
        if differences
        else [result.get("reason", "Review evidence")]
    )
    if errors:
        parts.append("Unavailable: " + ", ".join(errors))
    return "; ".join(parts)


def table_rows(report):
    rows = []
    has_agent = any(i.get("agent_review") or i.get("stale_agent_review") for i in report["items"])
    for item in report["items"]:
        result = item["validations"].get("correctness")
        methods = result.get("methods", []) if result else []
        found = sum(m.get("status") == "found" for m in methods)
        applicable = sum(m.get("status") != "not_applicable" for m in methods)
        agree = sum(m.get("agrees_with_consensus") is True for m in methods)
        rows.append(
            {
                "Citation key": item["entry"].get("key", ""),
                "Used in paper": {True: "Yes", False: "No", None: "Unknown"}[
                    item["validations"].get("is_used")
                ],
                "Status": correctness(item),
                **(
                    {"Agent": item.get("agent_review", {}).get("status", "Not checked")}
                    if has_agent
                    else {}
                ),
                "Found": f"{found}/{applicable}" if result else "—",
                "Consensus": f"{agree}/{found}" if result else "—",
                "Note": note(item),
                **(
                    {
                        "Agent note": item.get("agent_review", {}).get(
                            "summary", "Stale evidence" if item.get("stale_agent_review") else ""
                        )
                    }
                    if has_agent
                    else {}
                ),
            }
        )
    return rows


def display(value):
    if value is None or value == "" or value == []:
        return "—"
    if isinstance(value, list) and all(isinstance(v, dict) and "family" in v for v in value):
        return "; ".join(
            " ".join(str(v.get(k) or "") for k in ("given", "family", "suffix")).strip()
            for v in value
        )
    if isinstance(value, list) and all(
        isinstance(v, dict) and {"field", "value"} <= v.keys() for v in value
    ):
        return "; ".join(f"{v['field']}: {v['value']}" for v in value)
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def comparison_rows(item, show_matches=False):
    original = input_record(item["entry"])
    rows = []
    for comparison in item["validations"].get("correctness", {}).get("input_findings", []):
        rows.append(
            {
                "Source": "input",
                "Field": comparison["field"],
                "Status": field_status(comparison["result"]),
                "Your value": display(comparison.get("input")),
                "Source's value": comparison.get("message", "Input metadata is inconsistent"),
            }
        )
    for method in item["validations"].get("correctness", {}).get("methods", []):
        if not method.get("found_ref"):
            continue
        comparisons = method.get("comparisons") or compare_fields(original, method["found_ref"])
        for comparison in comparisons:
            state = comparison["result"]
            if not show_matches and state in {"match", "not_checked"}:
                continue
            rows.append(
                {
                    "Source": method["name"],
                    "Field": comparison["field"],
                    "Status": field_status(state),
                    "Your value": display(comparison.get("input")),
                    "Source's value": display(comparison.get("found")),
                }
            )
    for comparison in item.get("agent_review", {}).get("comparisons", []):
        if not show_matches and comparison["result"] == "match":
            continue
        rows.append(
            {
                "Source": "agent",
                "Field": comparison["field"],
                "Status": field_status(comparison["result"]),
                "Your value": display(comparison.get("input")),
                "Source's value": display(comparison.get("found")),
            }
        )
    return rows


def suggestions(item):
    result = item["validations"].get("correctness", {})
    agent_rows = [
        {
            "Field": c["field"],
            "Current": display(c.get("input")),
            "Suggested": display(c["found"]),
            "Source": "agent",
        }
        for c in item.get("agent_review", {}).get("comparisons", [])
        if c["result"] == "mismatch" and c.get("found") is not None
    ]
    if result.get("is_correct") is not False or result.get("complete") is False:
        return agent_rows
    rows = agent_rows
    seen = set()
    for method in result.get("methods", []):
        if not method.get("authority") or method.get("agrees_with_consensus") is not True:
            continue
        for difference in method.get("differences", []):
            if difference.get("found") is None:
                continue
            key = (difference["field"], display(difference["found"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "Field": difference["field"],
                    "Current": display(difference.get("input")),
                    "Suggested": display(difference["found"]),
                    "Source": method["name"],
                }
            )
    return rows


def source_rows(methods):
    """Saved source details, including historical and extension source identities."""
    from bib_lint.status import source_status

    return [
        {
            "Source": m["name"],
            "Name": m.get("display_name") or m["name"],
            "Status": ["Resolved" if m.get("redirect_url") else source_status(m["status"])],
            "URL": m.get("source_url")
            or (m.get("found_ref") or {}).get("url")
            or m.get("redirect_url"),
            "Lookup": lookup_label(m),
            "Revision": m.get("adapter_version", ""),
            "Search scope": "; ".join(
                dict.fromkeys(a["scope"] for a in m.get("lookup_provenance", []))
            ),
            "Error": m.get("error", {}).get("message", "") or m.get("reason", ""),
        }
        for m in methods
    ]


def lookup_label(method):
    if method.get("status") == "error" and method.get("requests") == []:
        return "Not queried"
    history = method.get("lookup_history", [])
    strategy = history[-1].get("strategy") if history else None
    return {
        "url": "Supplied link",
        "identifier": "Supplied identifier",
        "resolve": "DOI resolution",
        "search": "Source search",
    }.get(strategy, "Saved source check")


def cache_entries(cache_dir, citation_key):
    manifest = json.loads((Path(cache_dir) / "checksum.json").read_text())
    if manifest.get("algorithm") != "sha256" or not isinstance(manifest.get("files"), list):
        raise ValueError("Unsupported checksum manifest")
    return sorted(
        [e for e in manifest["files"] if e.get("citation_key") == citation_key],
        key=lambda e: e.get("cached_at", 0),
        reverse=True,
    )


def read_response(cache_dir, entry):
    root = Path(cache_dir).resolve()
    relative = Path(entry["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid cache path")
    path = root / relative
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError("Cache path is outside the cache directory or is a symlink")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
        raise ValueError("Checksum mismatch. Rerun verification to replace this response.")
    return raw, raw.decode(entry.get("encoding", "utf-8"), errors="replace")


def pretty_xml(text):
    document = minidom.parseString(text)
    try:
        return document.toprettyxml(indent="  ")
    finally:
        document.unlink()
