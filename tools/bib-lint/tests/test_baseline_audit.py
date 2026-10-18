"""Completion evidence must reject missing cases, modified evidence and bad scores."""

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from test_benchmarks import csv_bytes, report, snapshot, zenodo_rows

from evaluation.harness import read_predictions, run_split, write_predictions
from scripts.check_baseline import export_results, inspect, summary_rows


def fixture_run(root, *, tool_failure=False):
    snapshot(
        root, "zenodo", {"manual_reference_verification_dataset.csv": csv_bytes(zenodo_rows())}
    )

    def audit(path, **_):
        value = json.loads(path.read_text())
        key = value["items"][0]["entry"]["key"]
        if tool_failure and key.endswith("R2"):
            raise RuntimeError("Actual tool failure")
        value["items"][0]["validations"] = report(key, True, "found")["items"][0]["validations"]
        value["items"][0]["validations"]["correctness"]["methods"][0]["found_ref"] = {
            "title": value["items"][0]["entry"]["fields"]["title"],
            "authors": [],
            "identifiers": {},
        }
        return None, value, []

    # Save the normal audit artifact as the production audit does.
    def save_audit(path, **kwargs):
        result = audit(path, **kwargs)
        kwargs["output"].mkdir(parents=True, exist_ok=True)
        (kwargs["output"] / "report.json").write_text(json.dumps(result[1]))
        return result

    run_split("zenodo", "all", root, audit=save_audit, client=object())
    return root / "runs" / "zenodo" / "all"


def test_full_artifact_audit_accepts_native_results_and_rejects_wrong_metrics(tmp_path):
    folder = fixture_run(tmp_path)
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert result["complete"] and not result["errors"]
    assert result["verified_cases"] == result["expected_cases"] == 3
    path = folder / "evaluation.json"
    evaluation = json.loads(path.read_text())
    evaluation["protocol_metrics"]["accuracy"] = 0.99
    path.write_text(json.dumps(evaluation))
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert not result["complete"]
    assert any("metrics differ" in error for error in result["errors"])


def test_baseline_module_validates_available_cases_without_other_snapshots(tmp_path):
    fixture_run(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_baseline", "--root", str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["verified_cases"] == 3
    assert not value["complete"]
    assert "NameError" not in str(value["errors"])


def test_partial_runs_never_pass_completion_audit(tmp_path):
    folder = fixture_run(tmp_path)
    predictions = read_predictions(folder)
    write_predictions(folder / "predictions.jsonl", predictions[:1])
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert not result["complete"] and result["verified_cases"] == 1
    assert result["expected_cases"] == 3 and result["pending"]


def test_corrupted_input_and_evidence_are_detected(tmp_path):
    folder = fixture_run(tmp_path)
    prediction = read_predictions(folder)[0]
    case = tmp_path / prediction["case_dir"]
    cache = case / "audit" / "cache"
    cache.mkdir()
    (cache / "response.txt").write_text("tampered")
    (cache / "checksum.json").write_text(
        json.dumps({"files": [{"path": "response.txt", "sha256": "different"}]})
    )
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert not result["complete"] and any("checksum mismatch" in e for e in result["errors"])
    (cache / "checksum.json").unlink()
    path = case / "input.json"
    value = json.loads(path.read_text())
    value["items"][0]["entry"]["fields"]["title"] = "Changed citation"
    path.write_text(json.dumps(value))
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert not result["complete"] and any(
        "input or conversion differs" in e for e in result["errors"]
    )


def test_genuine_tool_failure_is_allowed_but_harness_failure_is_not(tmp_path):
    folder = fixture_run(tmp_path, tool_failure=True)
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert result["complete"] and result["verified_cases"] == 3
    predictions = read_predictions(folder)
    predictions[1]["failure_stage"] = "export"
    write_predictions(folder / "predictions.jsonl", predictions)
    result = inspect(tmp_path, benchmarks=["zenodo"])
    assert not result["complete"] and any("Harness failure: export" in e for e in result["errors"])


def test_final_summary_exports_only_verified_complete_results(tmp_path):
    fixture_run(tmp_path)
    result = inspect(tmp_path, benchmarks=["zenodo"])
    export_results(tmp_path, result)
    exported = json.loads((tmp_path / "baseline-results.json").read_text())
    assert exported["complete"] and exported["references"] == 3
    assert exported["summary"][0]["accuracy"] == 1 / 3
    assert (tmp_path / "baseline-results.csv").read_text().count("\n") == 2
    result["complete"] = False
    with pytest.raises(ValueError, match="requires a successful"):
        export_results(tmp_path, result)


def test_summary_preserves_official_modes_and_undefined_positive_only_metrics():
    coverage = {"official_cases": 10, "evaluated": 10, "definitive": 6}
    official = {
        "detection_rate": 0.5,
        "false_positive_rate": None,
        "f1_hallucination": 0.4,
        "coverage": 0.6,
    }
    result = {
        "coverage": coverage,
        "evaluation": "official_python_evaluator",
        "official_metrics": {"conservative": official, "aggressive": official},
        "supplementary_conservative_accuracy": 0.7,
    }
    positive = {
        "coverage": coverage,
        "evaluation": "positive_collection",
        "collection_summary": {"flagged_fraction_of_full_collection": 0.8},
    }
    rows = summary_rows(
        {
            "benchmarks": {
                "hallmark": {"stress_test": result},
                "gptzero": {"all": positive},
                "hallucitation": {"all": positive},
            }
        }
    )
    assert [r["mode"] for r in rows] == [
        "conservative",
        "aggressive",
        "positive_collection",
        "positive_collection",
    ]
    assert rows[0]["supplementary_accuracy"] == 0.7
    assert rows[1]["supplementary_accuracy"] is None
    assert all(r["accuracy"] is None for r in rows)
    assert all(r["precision"] is None and r["recall"] is None for r in rows[2:])
    assert all(r["flagged_fraction"] == 0.8 for r in rows[2:])


def test_final_exports_encode_undefined_upstream_metrics_as_null(tmp_path):
    fixture_run(tmp_path)
    result = inspect(tmp_path, benchmarks=["zenodo"])
    metrics = result["benchmarks"]["zenodo"]["all"]["protocol_metrics"]
    metrics["false_positive_rate"] = float("nan")
    result["benchmarks"]["zenodo"]["all"]["unsupported_metrics"] = {
        "tiers": [float("inf"), float("-inf")]
    }
    export_results(tmp_path, result)

    def reject_constant(value):
        raise ValueError(f"Nonstandard JSON constant: {value}")

    exported = json.loads(
        (tmp_path / "baseline-results.json").read_text(), parse_constant=reject_constant
    )
    assert exported["summary"][0]["false_positive_rate"] is None
    assert exported["summary"][0]["accuracy"] == 1 / 3
    assert exported["benchmarks"]["zenodo"]["all"]["unsupported_metrics"]["tiers"] == [
        None,
        None,
    ]
    assert math.isnan(metrics["false_positive_rate"])
    csv_text = (tmp_path / "baseline-results.csv").read_text()
    assert "nan" not in csv_text.lower() and "inf" not in csv_text.lower()
