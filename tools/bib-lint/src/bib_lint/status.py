"""Shared status vocabulary for reference decisions, lookups, and field checks.

Stored schema-v2 tokens stay compatible with saved reports and resume checkpoints.
A failed lookup is not evidence that a reference is invalid.
"""

STATUS_COLORS = {
    "Correct": "green",
    "Invalid": "red",
    "Pending": "orange",
    "Skipped": "gray",
    "Not applicable": "gray",
    "Not checked": "gray",
    "Unresolved": "red",
    "Partial match": "orange",
    "Needs review": "orange",
    "Insufficient data": "orange",
    "Found": "green",
    "Not found": "orange",
    "Ambiguous": "orange",
    "Failed": "red",
    "Match": "green",
    "Mismatch": "red",
}

SOURCE_LABELS = {
    "found": "Found",
    "not_found": "Not found",
    "ambiguous": "Ambiguous",
    "error": "Failed",
    "not_applicable": "Not applicable",
}

FIELD_LABELS = {
    "match": "Match",
    "mismatch": "Mismatch",
    "unknown": "Insufficient data",
    "partial_match": "Partial match",
    "not_checked": "Not checked",
}


def reference_status(validations):
    if validations.get("is_used") is False:
        return "Skipped"
    result = validations.get("correctness")
    if not result:
        return "Pending"
    if result.get("complete") is False:
        return "Pending"
    verdict = result.get("is_correct")
    if validations.get("extraction", {}).get("state") == "needs_review" and verdict is not False:
        return "Needs review"
    if verdict is not None:
        return "Correct" if verdict else "Invalid"
    sources = result.get("methods", [])
    found = [s for s in sources if s.get("found_ref")]
    if not found:
        return (
            "Needs review"
            if result.get("input_findings") or any(s.get("candidates") for s in sources)
            else "Unresolved"
        )
    comparisons = [c for s in found for c in s.get("comparisons", [])]
    if (
        any(c.get("result") == "partial_match" for c in comparisons)
        and not result.get("input_findings")
        and all(c.get("result") in {"match", "partial_match", "not_checked"} for c in comparisons)
        and all(s.get("agrees_with_consensus") is True for s in found)
        and any(s.get("authority") for s in found)
        and not any(s.get("version_uncertain") for s in found)
        and not any(s.get("status") == "ambiguous" for s in sources)
    ):
        return "Partial match"
    return "Needs review"


def source_status(value):
    return SOURCE_LABELS.get(value, "Unresolved")


def field_status(value):
    return FIELD_LABELS.get(value, "Unresolved")
