"""Read-only, entry-bound agent evidence. Never participates in API consensus."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

REVIEW_STATUSES = {"Correct", "Invalid", "Partial match", "Needs review", "Unresolved"}


def entry_digest(entry):
    raw = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def sidecar_path(report_path):
    path = Path(report_path)
    name = path.name.removesuffix(".json").removesuffix(".tmp")
    return path.with_name(name + ".agent.json")


def attach_reviews(report, path):
    """Attach presentation-only reviews; reject malformed data and quarantine stale entries."""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("source") != "agent":
        raise ValueError("Unsupported agent evidence schema")
    if not isinstance(data.get("items"), list):
        raise ValueError("Agent evidence must contain an items list")
    indexed = _index_reviews(data)
    warnings = []
    for item in report["items"]:
        review = indexed.pop(item["entry"].get("key"), None)
        if review is None:
            continue
        if review.get("entry_sha256") != entry_digest(item["entry"]):
            item["stale_agent_review"] = review
            warnings.append(
                f"Agent evidence is stale for {review['citation_key']}; rerun its review."
            )
        else:
            item["agent_review"] = review
    if indexed:
        warnings.append(f"Ignored agent evidence for {len(indexed)} keys absent from this report.")
    return warnings


def _index_reviews(data):
    indexed = {}
    for review in data["items"]:
        key = _validate_review(review, indexed)
        indexed[key] = review
    return indexed


def _validate_review(review, indexed):
    key = review.get("citation_key")
    if not isinstance(key, str) or key in indexed:
        raise ValueError("Agent evidence has a missing or duplicate citation key")
    if review.get("status") not in REVIEW_STATUSES:
        raise ValueError(f"Invalid agent status for {key}")
    for field in ("summary", "reviewed_at", "entry_sha256"):
        if not isinstance(review.get(field), str) or not review[field]:
            raise ValueError(f"Agent review requires {field} for {key}")
    if not isinstance(review.get("checked_fields"), list):
        raise ValueError(f"Agent review requires checked_fields for {key}")
    evidence = review.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"Agent review requires evidence for {key}")
    _validate_evidence(evidence, key)
    if not isinstance(review.get("comparisons", []), list):
        raise ValueError(f"Invalid agent comparisons for {key}")
    for comparison in review.get("comparisons", []):
        if not comparison.get("field") or comparison.get("result") not in {
            "match",
            "mismatch",
            "partial_match",
            "unknown",
            "not_checked",
        }:
            raise ValueError(f"Invalid agent field comparison for {key}")
    return key


def _validate_evidence(evidence, key):
    for source in evidence:
        url = urlsplit(source.get("url", ""))
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError(f"Invalid evidence URL for {key}")
        if not source.get("supports"):
            raise ValueError(f"Evidence must explain its support for {key}")
