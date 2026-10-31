"""Browser-ready audit data, independent of the HTTP server and verifier."""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from bib_lint.verification.matching import input_record
from bib_lint.viewer.data import comparison_rows, display, source_rows, suggestions, table_rows

ATTENTION = {"Invalid", "Unresolved", "Partial match", "Needs review"}


def reference_rows(report):
    rows = table_rows(report)
    for row, item in zip(rows, report["items"], strict=True):
        methods = item["validations"].get("correctness", {}).get("methods", [])
        failed = any(method.get("status") == "error" for method in methods)
        extraction = item["validations"].get("extraction", {})
        extraction_warning = extraction.get("state") == "needs_review"
        diagnostics = extraction.get("diagnostics", [])
        if diagnostics:
            row["Note"] += "; PDF extraction: " + "; ".join(d["message"] for d in diagnostics)
        row.update(
            title=item["entry"].get("fields", {}).get("title", ""),
            source_failed=failed,
            needs_attention=(
                row["Status"] in ATTENTION
                or row.get("Agent") in ATTENTION
                or failed
                or extraction_warning
            ),
        )
    return rows


def summary(report, rows):
    scope = report.get("verification_scope")
    eligible = (
        set(scope["eligible_keys"])
        if scope
        else {row["Citation key"] for row in rows if row["Used in paper"] == "Yes"}
    )
    checked = [row for row in rows if row["Citation key"] in eligible]
    counts = Counter(row["Status"] for row in checked)
    unknown = any(row["Used in paper"] == "Unknown" for row in rows)
    return {
        "total": len(rows),
        "eligible": len(checked),
        "completed": sum(row["Status"] not in {"Pending", "Skipped"} for row in checked),
        "used": None if unknown or (scope and scope["mode"] == "all") else len(checked),
        "skipped": sum(row["Status"] == "Skipped" for row in rows),
        "attention": sum(row["needs_attention"] for row in checked),
        "statuses": dict(counts),
        "agent_reviewed": sum(bool(item.get("agent_review")) for item in report["items"]),
        "scope": scope["mode"] if scope else "used" if not unknown else "unknown",
        **({"extraction": extraction_summary(report)} if "extraction" in report else {}),
    }


def extraction_summary(report):
    extraction = report["extraction"]
    return {
        "state": extraction["state"],
        "occurrence_count": len(report["items"]),
        "unresolved_fragments": extraction["unresolved_fragments"],
        "reference_pages": extraction["reference_pages"],
        "diagnostics": extraction["diagnostics"],
    }


def metadata(report, path):
    path = Path(path)
    if path.is_dir():
        checkpoint = path / "report.tmp.json"
        path = checkpoint if checkpoint.exists() else path / "report.json"
    if not path.exists() and path.name.endswith(".tmp.json"):
        path = path.with_name(path.name[:-9] + ".json")
    source = report.get("source")
    if isinstance(source, dict):
        source = source.get("name")
    return {
        "report_path": str(path),
        "bibliography": report.get("audit_input", {}).get("path") or source,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "input_kind": "pdf" if "extraction" in report else "bibliography",
    }


def reference_detail(item):
    result = item["validations"].get("correctness", {})
    row = table_rows({"items": [item]})[0]
    return {
        "entry": item["entry"],
        "row": row,
        "authors": display(input_record(item["entry"]).get("authors", [])),
        "reason": result.get("reason") or row["Note"],
        "suggestions": suggestions(item),
        "comparisons": comparison_rows(item, show_matches=True),
        "sources": source_rows(result.get("methods", [])),
        "methods": result.get("methods", []),
        "agent_review": item.get("agent_review"),
        **(
            {"pdf": item["pdf"], "extraction": item["validations"]["extraction"]}
            if "pdf" in item
            else {}
        ),
    }
