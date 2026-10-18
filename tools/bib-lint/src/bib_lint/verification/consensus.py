"""Evidence-based decisions; agreement is not a vote that overrides primary records."""

from bib_lint.verification.matching import compare_fields, same_record


def build_consensus(methods):
    found = [m for m in methods if m["status"] == "found"]
    selected, reason = _select_cluster(found)
    for method in found:
        method["agrees_with_consensus"] = None if selected is None else method in selected
    applicable = [m for m in methods if m["status"] != "not_applicable"]
    agree = len(selected or [])
    consensus = {
        "agree": agree,
        "total": len(found),
        "applicable": len(applicable),
        "display": f"{agree}/{len(found)}",
        "records_found": len(found),
        "disagree": len(found) - agree if selected is not None else 0,
        "unresolved_records": len(found) if selected is None else 0,
        "unavailable": sum(m["status"] == "error" for m in methods),
        "not_found": sum(m["status"] == "not_found" for m in methods),
        "ambiguous": sum(m["status"] == "ambiguous" for m in methods),
        "not_applicable": len(methods) - len(applicable),
    }
    correct = None
    canonical = None
    if selected:
        primary = [m for m in selected if m.get("authority")]
        if primary:
            preferred = sorted(primary, key=lambda m: (m.get("canonical_priority", 9), m["name"]))
            canonical = preferred[0]["found_ref"]
            correct, reason = _primary_decision(primary, methods, reason)
    return {
        "is_correct": correct,
        "consensus": consensus,
        "methods": methods,
        "canonical_ref": canonical,
        "reason": reason,
        "policy_version": 5,
        "checked_fields": ["title", "authors", "year", "venue", "doi", "arxiv"],
        "scope": "Core citation metadata only; not claim support, pages, volume, or edition",
    }


def _select_cluster(found):
    clusters = []
    for method in found:
        for cluster in clusters:
            if all(same_record(method["found_ref"], other["found_ref"]) for other in cluster):
                cluster.append(method)
                break
        else:
            clusters.append([method])
    authoritative = [c for c in clusters if any(m.get("authority") for m in c)]
    selected = None
    reason = "No unambiguous authoritative record found"
    if len(authoritative) == 1:
        selected = authoritative[0]
        reason = "Authoritative record selected; index agreement is supporting evidence"
    elif len(authoritative) > 1:
        reason = "Authoritative sources identify conflicting records or publication versions"
    elif clusters:
        ranked = sorted(clusters, key=len, reverse=True)
        if len(ranked) == 1 or len(ranked[0]) > len(ranked[1]):
            selected = ranked[0]
            reason = "Indexes agree, but no authoritative record has been verified"
        else:
            reason = "No unique consensus among index records"
    return selected, reason


def _primary_decision(primary, methods, reason):
    correct = None
    conflicting = any(
        any(c["result"] == "mismatch" for c in compare_fields(a["found_ref"], b["found_ref"]))
        for a in primary
        for b in primary
        if a is not b
    )
    # An ambiguous primary search may represent another edition; don't hide it.
    ambiguous_primary = any(m.get("authority") and m["status"] == "ambiguous" for m in methods)
    if any(m.get("version_uncertain") for m in primary):
        reason = "Preprint/publication version differences require review"
    elif conflicting or ambiguous_primary:
        reason = "Authoritative metadata conflicts or an authoritative lookup is ambiguous"
    elif any(m.get("differences") for m in primary):
        correct = False
        reason = "Authoritative record demonstrates a field discrepancy"
    elif all(
        c["result"] in {"match", "not_checked"} for m in primary for c in m.get("comparisons", [])
    ):
        correct = True
        reason = "Checked citation fields match the authoritative record"
    elif any(c["result"] == "partial_match" for m in primary for c in m.get("comparisons", [])):
        reason = "Listed authors match in order; the bibliography omits remaining authors"
    else:
        reason = "Record identified, but some citation fields remain unverified"
    return correct, reason
