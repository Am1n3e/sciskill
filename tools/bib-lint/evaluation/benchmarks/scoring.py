"""Export official predictions and dispatch to the available evaluation protocol."""

import csv
import importlib.metadata
import io
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime

from bib_lint.status import reference_status
from bib_lint.storage import write_json
from evaluation.benchmarks.common import digest
from evaluation.benchmarks.sources import HALLMARK_REVISION

MAPPING_VERSION = 1


def prediction_from_report(report, elapsed=0):
    if len(report["items"]) != 1:
        raise ValueError("Benchmark audits must contain exactly one reference")
    item = report["items"][0]
    correctness = item["validations"].get("correctness", {})
    methods = correctness.get("methods", [])
    status = reference_status(item["validations"])
    errors = [
        {"provider": m["name"], **m.get("error", {})} for m in methods if m.get("status") == "error"
    ]
    complete = correctness.get("complete", True) and bool(correctness)
    usable = any(m.get("status") in {"found", "not_found", "ambiguous"} for m in methods)
    evaluated = complete and (usable or not errors)
    label = (
        "VALID" if status == "Correct" else "HALLUCINATED" if status == "Invalid" else "UNCERTAIN"
    )
    # Zenodo's published protocol flags unresolved and review-required results.
    # Source failures without usable evidence remain unevaluated, not false claims.
    flagged = None if not evaluated else status != "Correct"
    requests = [r for m in methods for r in m.get("requests", [])]
    return {
        "id": item["entry"]["key"],
        "label": label,
        "confidence": 0.5,
        "reason": correctness.get("reason", status),
        "evaluated": evaluated,
        "flagged": flagged,
        "status": status,
        "source_errors": errors,
        "sources": [m["name"] for m in methods if m.get("status") != "not_applicable"],
        "wall_clock_seconds": elapsed,
        "api_calls": sum(not r.get("cached", False) for r in requests),
    }


def unavailable_prediction(case_id, reason):
    return {
        "id": case_id,
        "label": "UNCERTAIN",
        "confidence": 0.5,
        "reason": reason,
        "evaluated": False,
        "flagged": None,
        "status": "Not evaluated",
        "source_errors": [],
        "sources": [],
        "wall_clock_seconds": 0,
        "api_calls": 0,
    }


def check_official_evaluator():
    try:
        distribution = importlib.metadata.distribution("hallmark")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError("Install the official scorer with: uv sync --group benchmark") from exc
    source = json.loads(distribution.read_text("direct_url.json") or "{}")
    if source.get("vcs_info", {}).get("commit_id") != HALLMARK_REVISION:
        raise ValueError("HALLMARK evaluator revision differs from the pinned official dataset")


def coverage(cases, predictions):
    expected = {c.id for c in cases}
    counts = Counter(p["id"] for p in predictions)
    if set(counts) - expected or any(n != 1 for n in counts.values()):
        raise ValueError("Predictions contain duplicate or unknown benchmark IDs")
    present = {p["id"]: p for p in predictions}
    # Preserve the full denominator, even when the official scorer permits partial runs.
    aligned = [present.get(c.id, unavailable_prediction(c.id, "Not run")) for c in cases]
    return aligned, {
        "official_cases": len(cases),
        "attempted": len(predictions),
        "evaluated": sum(p["evaluated"] for p in aligned),
        "definitive": sum(p["evaluated"] and p["label"] != "UNCERTAIN" for p in aligned),
        "source_errors": dict(Counter(e["provider"] for p in aligned for e in p["source_errors"])),
        "failure_stages": dict(
            Counter(p["failure_stage"] for p in aligned if p.get("failure_stage"))
        ),
    }


def binary_metrics(cases, aligned):
    """Reproduce the documented binary protocol, only when every case is evaluable."""
    if any(p["flagged"] is None for p in aligned):
        return None
    tp = sum(c.issue and p["flagged"] for c, p in zip(cases, aligned, strict=True))
    fp = sum(not c.issue and p["flagged"] for c, p in zip(cases, aligned, strict=True))
    tn = sum(not c.issue and not p["flagged"] for c, p in zip(cases, aligned, strict=True))
    fn = sum(c.issue and not p["flagged"] for c, p in zip(cases, aligned, strict=True))

    def ratio(a, b):
        return a / b if b else None

    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": ratio(tp + tn, len(cases)),
        "precision": precision,
        "recall": recall,
        "false_positive_rate": ratio(fp, fp + tn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def score(name, split, cases, predictions, folder, source_folder):
    aligned, conditions = coverage(cases, predictions)
    result = {
        "benchmark": name,
        "split": split,
        "coverage": conditions,
        "mapping_version": MAPPING_VERSION,
        "complete": conditions["attempted"] == len(cases),
        "harness_ok": not any(stage != "bib_lint" for stage in conditions["failure_stages"]),
        "confidence_note": "bib-lint has no calibrated confidence; 0.5 is an export placeholder",
    }
    if name == "hallmark":
        check_official_evaluator()
        from hallmark.dataset.schema import Prediction, load_entries
        from hallmark.evaluation.metrics import build_confusion_matrix, evaluate

        entries = load_entries(source_folder / f"{split}.jsonl")
        official = [
            Prediction(
                bibtex_key=p["id"],
                label=p["label"],
                confidence=p["confidence"],
                reason=p["reason"],
                evaluated=p["evaluated"],
                api_sources_queried=p["sources"],
                api_calls=p["api_calls"],
                wall_clock_seconds=p["wall_clock_seconds"],
            )
            for p in aligned
        ]
        (folder / "official_predictions.jsonl").write_text(
            "".join(p.to_json() + "\n" for p in official)
        )
        official_results = evaluate(
            entries, official, tool_name="bib-lint", split_name=split, eval_mode="both"
        )
        for value in official_results.values():
            value.split_sha256 = digest((source_folder / f"{split}.jsonl").read_bytes())
            value.source_condition = conditions
            value.run_timestamp = datetime.now(UTC).isoformat()
            value.tool_version = importlib.metadata.version("bib-lint")
        result["evaluator_revision"] = HALLMARK_REVISION
        result["evaluation"] = "official_python_evaluator"
        result["official_metrics"] = {k: asdict(v) for k, v in official_results.items()}
        cm = build_confusion_matrix(entries, official)
        total = cm.tp + cm.fp + cm.tn + cm.fn
        result["supplementary_conservative_accuracy"] = (cm.tp + cm.tn) / total if total else None
        result["classification_warning"] = (
            "Official conservative scoring excludes abstentions; inspect coverage. Aggressive "
            "scoring promotes uncertainty/missing answers to hallucinated. Calibration metrics "
            "are not meaningful with constant confidence."
        )
    elif name == "zenodo":
        result["evaluation"] = "documented_binary_protocol_no_released_scorer"
        result["protocol_metrics"] = binary_metrics(cases, aligned)
        rows = [
            {
                **c.original,
                "bib_lint": "not_evaluated"
                if p["flagged"] is None
                else "flagged"
                if p["flagged"]
                else "not_flagged",
            }
            for c, p in zip(cases, aligned, strict=True)
        ]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=[*cases[0].original, "bib_lint"])
        writer.writeheader()
        writer.writerows(rows)
        (folder / "official_format_results.csv").write_text(buffer.getvalue())
        if result["protocol_metrics"] is None:
            result["classification_warning"] = (
                "No full-dataset binary metrics until every case is evaluated"
            )
    elif name in {"gptzero", "hallucitation"}:
        result["evaluation"] = (
            "positive_only_collection_no_official_scorer"
            if name == "gptzero"
            else "published_positive_only_appendix_no_official_scorer"
        )
        flagged = sum(p["flagged"] is True for p in aligned)
        result["collection_summary"] = {
            "flagged": flagged,
            "reported_issues": len(cases),
            "flagged_fraction_of_full_collection": flagged / len(cases),
        }
        result["classification_warning"] = (
            "No official scoring implementation or negative examples are published. This is "
            "detection coverage on the reported-positive collection, not an accuracy estimate."
        )
    write_json(folder / "evaluation.json", result)
    return result
