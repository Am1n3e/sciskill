"""Invoke CLI contracts, exercised without starting live benchmark audits."""

import subprocess
import sys
from pathlib import Path


def test_benchmark_namespace_accepts_positional_datasets_and_chained_tasks():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "invoke",
            "--dry",
            "benchmark.init",
            "benchmark.run",
            "hallmark",
            "--split",
            "dev_public",
            "--limit",
            "10",
            "benchmark.score",
            "zenodo",
            "benchmark.verify",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prepare --benchmark all" in result.stdout
    assert "run --benchmark hallmark --split dev_public" in result.stdout
    assert "--limit 10" in result.stdout
    assert "score --benchmark zenodo" in result.stdout
    assert "python -m scripts.check_baseline" in result.stdout


def test_benchmark_run_requires_an_explicit_dataset():
    result = subprocess.run(
        [sys.executable, "-m", "invoke", "--dry", "benchmark.run"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "required positional arguments: 'name'" in result.stderr
    assert "evaluation.harness run" not in result.stdout
