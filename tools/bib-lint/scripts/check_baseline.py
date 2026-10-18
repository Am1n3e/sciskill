"""Independently audit completed benchmark artifacts and assemble baseline results.

This command does not modify the running harness or contact metadata providers.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bib_lint.scope import validate_report
from bib_lint.storage import write_json
from evaluation.benchmarks.common import digest
from evaluation.benchmarks.conversion import make_report
from evaluation.benchmarks.scoring import check_official_evaluator, coverage, prediction_from_report
from evaluation.benchmarks.sources import BENCHMARKS, HALLMARK_REVISION, load_cases, verify_snapshot
from evaluation.harness import DEFAULT_ROOT, read_predictions, tool_identity


def primitive(value):
    return json.loads(json.dumps(value))


def portable_values(value):
    """Represent undefined upstream numbers without nonstandard JSON constants."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: portable_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable_values(item) for item in value]
    return value


def independently_count_binary(cases, predictions):
    if any(p["flagged"] is None for p in predictions):
        return None
    counts = Counter(
        (bool(c.issue), bool(p["flagged"])) for c, p in zip(cases, predictions, strict=True)
    )
    tp, fp, tn, fn = (
        counts[True, True],
        counts[False, True],
        counts[False, False],
        counts[True, False],
    )

    def divide(numerator, denominator):
        return numerator / denominator if denominator else None

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": divide(tp + tn, len(cases)),
        "precision": divide(tp, tp + fp),
        "recall": divide(tp, tp + fn),
        "false_positive_rate": divide(fp, fp + tn),
        "f1": divide(2 * tp, 2 * tp + fp + fn),
    }


def check_case(root, case, prediction):
    expected_folder = (
        Path("runs") / case.benchmark / case.split / "cases" / digest(case.id.encode())[:24]
    )
    if prediction["case_dir"] != str(expected_folder):
        raise ValueError("Prediction points to a different case folder")
    folder = root / expected_folder
    expected_input, expected_conversion = make_report(case)
    actual_input = json.loads((folder / "input.json").read_text())
    actual_conversion = json.loads((folder / "conversion.json").read_text())
    validate_report(actual_input)
    if actual_input != primitive(expected_input) or actual_conversion != primitive(
        expected_conversion
    ):
        raise ValueError("Case input or conversion differs from the official source adapter")
    if prediction.get("failure_stage"):
        if prediction["failure_stage"] != "bib_lint":
            raise ValueError(
                f"Harness failure: {prediction['failure_stage']}: {prediction['reason']}"
            )
        error = json.loads((folder / "tool-error.json").read_text())
        if error["stage"] != "bib_lint" or error["id"] != case.id or prediction["evaluated"]:
            raise ValueError("Tool-failure artifact does not match its prediction")
        return 0
    report = json.loads((folder / "audit" / "report.json").read_text())
    validate_report(report)
    if report["items"][0]["entry"] != actual_input["items"][0]["entry"]:
        raise ValueError("Auditing changed the input reference")
    native = prediction_from_report(report, prediction["wall_clock_seconds"])
    if any(prediction[key] != value for key, value in native.items()):
        raise ValueError("Prediction differs from the saved native bib-lint report")
    return _check_evidence(folder, report)


def check_scores(name, split, cases, predictions, folder, sources):
    result = json.loads((folder / "evaluation.json").read_text())
    aligned, counts = coverage(cases, predictions)
    if not result["complete"] or not result["harness_ok"] or result["coverage"] != counts:
        raise ValueError("Stored evaluation has incomplete or inconsistent coverage")
    if name == "hallmark":
        _check_hallmark_scores(split, cases, aligned, folder, sources, result)
    elif name == "zenodo":
        if result["protocol_metrics"] != independently_count_binary(cases, aligned):
            raise ValueError("Published-protocol metrics differ from prediction counts")
        with (folder / "official_format_results.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        expected = [
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
        if rows != expected:
            raise ValueError("Official CSV export differs from original rows and predictions")
    else:
        flagged = sum(p["flagged"] is True for p in aligned)
        if result["collection_summary"] != {
            "flagged": flagged,
            "reported_issues": len(cases),
            "flagged_fraction_of_full_collection": flagged / len(cases),
        }:
            raise ValueError("Positive-collection metrics differ from full case counts")
    return result


def inspect(root, *, benchmarks=None):
    root = Path(root).absolute()
    names = list(BENCHMARKS) if benchmarks is None else benchmarks
    summary = {
        "root": str(root),
        "checked_at": datetime.now(UTC).isoformat(),
        "benchmarks": {},
        "errors": [],
        "pending": [],
        "verified_cases": 0,
        "expected_cases": 0,
        "verified_evidence_files": 0,
    }
    identity = tool_identity()
    for name in names:
        summary["benchmarks"][name] = {}
        try:
            source = verify_snapshot(root / "sources" / name)
            for split in BENCHMARKS[name]["splits"]:
                cases = load_cases(name, split, root)
                summary["expected_cases"] += len(cases)
                folder = root / "runs" / name / split
                if not (folder / "run-config.json").exists():
                    summary["pending"].append(f"{name}/{split}: not started")
                    continue
                config = json.loads((folder / "run-config.json").read_text())
                if config["identity"] != identity or config["source_files"] != source["files"]:
                    raise ValueError("Run configuration differs from current frozen code or inputs")
                predictions = read_predictions(folder)
                coverage(cases, predictions)  # Reject duplicate/unknown IDs independently.
                by_id = {p["id"]: p for p in predictions}
                for case in cases:
                    if case.id not in by_id:
                        continue
                    try:
                        summary["verified_evidence_files"] += check_case(root, case, by_id[case.id])
                        summary["verified_cases"] += 1
                    except (ValueError, OSError, KeyError) as exc:
                        summary["errors"].append(f"{name}/{split}/{case.id}: {exc}")
                if len(predictions) != len(cases):
                    summary["pending"].append(
                        f"{name}/{split}: {len(predictions)}/{len(cases)} completed"
                    )
                    continue
                summary["benchmarks"][name][split] = check_scores(
                    name, split, cases, predictions, folder, root / "sources" / name
                )
        except (ValueError, OSError, KeyError) as exc:
            summary["errors"].append(f"{name}: {exc}")
    summary["complete"] = (
        not summary["pending"]
        and not summary["errors"]
        and summary["verified_cases"] == summary["expected_cases"]
    )
    return summary


def summary_rows(audit):
    """Keep differing upstream metrics separate; never pool overlapping datasets."""
    rows = []
    for name, splits in audit["benchmarks"].items():
        for split, result in splits.items():
            base = {
                "benchmark": name,
                "split": split,
                "evaluation": result["evaluation"],
                "references": result["coverage"]["official_cases"],
                "evaluated": result["coverage"]["evaluated"],
                "definitive": result["coverage"]["definitive"],
                "accuracy": None,
                "precision": None,
                "recall": None,
                "false_positive_rate": None,
                "f1": None,
                "flagged_fraction": None,
                "classification_coverage": None,
            }
            if name == "hallmark":
                for mode, metrics in result["official_metrics"].items():
                    rows.append(
                        {
                            **base,
                            "mode": mode,
                            "supplementary_accuracy": result["supplementary_conservative_accuracy"]
                            if mode == "conservative"
                            else None,
                            "recall": metrics["detection_rate"],
                            "false_positive_rate": metrics["false_positive_rate"],
                            "f1": metrics["f1_hallucination"],
                            "classification_coverage": metrics["coverage"],
                        }
                    )
            elif name == "zenodo":
                metrics = result["protocol_metrics"] or {}
                rows.append(
                    {
                        **base,
                        "mode": "published_binary_protocol",
                        "supplementary_accuracy": None,
                        **{
                            k: metrics.get(k)
                            for k in [
                                "accuracy",
                                "precision",
                                "recall",
                                "false_positive_rate",
                                "f1",
                            ]
                        },
                    }
                )
            else:
                rows.append(
                    {
                        **base,
                        "mode": "positive_collection",
                        "supplementary_accuracy": None,
                        "flagged_fraction": result["collection_summary"][
                            "flagged_fraction_of_full_collection"
                        ],
                    }
                )
    return rows


def export_results(root, audit):
    if not audit["complete"]:
        raise ValueError("Final baseline export requires a successful full completion audit")
    rows = portable_values(summary_rows(audit))
    write_json(
        root / "baseline-results.json",
        portable_values(
            {
                "complete": True,
                "verified_at": audit["checked_at"],
                "references": audit["expected_cases"],
                "summary": rows,
                "benchmarks": audit["benchmarks"],
                "interpretation": (
                    "HALLMARK uses its official evaluator in both uncertainty modes. Zenodo uses "
                    "the published binary protocol. GPTZero and HalluCitation are positive-only "
                    "collections, so only detection fractions are reported. Scores are not pooled. "
                    "Calibration metrics use placeholder confidence and are not interpretable. "
                    "Non-finite upstream metrics are null in this export; original evaluator "
                    "outputs are retained in each split's evaluation.json."
                ),
            }
        ),
    )
    with (root / "baseline-results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    result = inspect(args.root)
    write_json(args.root / "baseline-verification.json", result)
    if result["complete"]:
        export_results(args.root, result)
    print(
        json.dumps({key: value for key, value in result.items() if key != "benchmarks"}, indent=2)
    )
    return 0 if result["complete"] else 2


def _check_evidence(folder, report):
    cache = folder / "audit" / "cache"
    path = cache / "checksum.json"
    manifest = json.loads(path.read_text()) if path.exists() else {"files": []}
    tracked = {}
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe evidence path")
        if hashlib.sha256((cache / relative).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Evidence checksum mismatch: {relative}")
        tracked[item["path"]] = item["sha256"]
    for method in report["items"][0]["validations"]["correctness"].get("methods", []):
        for request in method.get("requests", []):
            for evidence in [request, *request.get("responses", [])]:
                if evidence.get("cache_file") and tracked.get(
                    evidence["cache_file"]
                ) != evidence.get("sha256"):
                    raise ValueError("Report evidence is absent from the verified cache")
    return len(tracked)


def _check_hallmark_scores(split, cases, aligned, folder, sources, result):
    check_official_evaluator()
    from hallmark.dataset.schema import Prediction, load_entries
    from hallmark.evaluation.metrics import build_confusion_matrix, evaluate

    entries = load_entries(sources / f"{split}.jsonl")
    if [(e.bibtex_key, e.fields, e.label == "HALLUCINATED") for e in entries] != [
        (c.id, c.fields, c.issue) for c in cases
    ]:
        raise ValueError("Harness cases differ from the official HALLMARK loader")
    rows = [
        json.loads(line)
        for line in (folder / "official_predictions.jsonl").read_text().splitlines()
    ]
    official = [Prediction.from_dict(row) for row in rows]
    expected = [
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
    if [asdict(p) for p in official] != [asdict(p) for p in expected]:
        raise ValueError("Official prediction export differs from native predictions")
    metric_results = evaluate(
        entries, official, tool_name="bib-lint", split_name=split, eval_mode="both"
    )
    ignored = {"tool_version", "split_sha256", "run_timestamp", "source_condition"}
    for mode, metrics in metric_results.items():
        actual = result["official_metrics"][mode]
        if any(
            actual[key] != value
            for key, value in primitive(asdict(metrics)).items()
            if key not in ignored
        ):
            raise ValueError(f"Stored {mode} metrics differ from the official evaluator")
        if actual["split_sha256"] != digest((sources / f"{split}.jsonl").read_bytes()):
            raise ValueError("Official metrics are stamped with a different dataset hash")
        if actual["tool_version"] != importlib.metadata.version("bib-lint"):
            raise ValueError("Official metrics describe a different tool version")
    if result["evaluator_revision"] != HALLMARK_REVISION:
        raise ValueError("Official evaluator revision differs from the pinned release")
    cm = build_confusion_matrix(entries, official)
    total = cm.tp + cm.tn + cm.fp + cm.fn
    accuracy = (cm.tp + cm.tn) / total if total else None
    if result["supplementary_conservative_accuracy"] != accuracy:
        raise ValueError("Supplementary accuracy differs from official confusion counts")


if __name__ == "__main__":
    raise SystemExit(main())
