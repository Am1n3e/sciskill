"""Benchmark tasks loaded by the root Invoke collection as ``benchmark.*``."""

import shlex
from pathlib import Path

from invoke import task

ROOT = Path(__file__).resolve().parents[1]


BENCHMARK_HELP = {
    "name": "Dataset: all, hallmark, zenodo, gptzero, or hallucitation.",
    "root": (
        "Artifact directory; defaults to evaluation/.artifacts. "
        "Use a fresh root after code changes."
    ),
}
SPLIT_HELP = "One official split; requires a single benchmark. Defaults to every split."


def _benchmark_python(context, module, arguments, root):
    command = ["uv", "run", "--locked", "--group", "benchmark", "python", "-m", module]
    command.extend(arguments)
    if root:
        command.extend(["--root", root])
    with context.cd(str(ROOT)):
        context.run(shlex.join(command), echo=True)


def _benchmark_harness(context, command, benchmark, split, root, extra=()):
    arguments = [command, "--benchmark", benchmark]
    if split:
        arguments.extend(["--split", split])
    arguments.extend(extra)
    _benchmark_python(context, "evaluation.harness", arguments, root)


@task(help={**BENCHMARK_HELP, "name": BENCHMARK_HELP["name"] + " Defaults to all."})
def init(context, name="all", root=""):
    """Install the locked benchmark scorer and download or verify frozen datasets."""
    with context.cd(str(ROOT)):
        context.run("uv sync --locked --group benchmark", echo=True)
    _benchmark_harness(context, "prepare", name, "", root)


@task(
    positional=["name"],
    help={
        **BENCHMARK_HELP,
        "split": SPLIT_HELP,
        "limit": "First N cases per split for a partial smoke run; 0 means the full dataset.",
        "workers": "Concurrent references with shared host pacing (default: 8).",
        "retry_errors": "Retry failed cases and provider errors when resuming.",
        "verbose": "Print provider progress while auditing references.",
    },
)
def run(
    context,
    name,
    split="",
    root="",
    limit=0,
    workers=8,
    retry_errors=False,
    verbose=False,
):
    """Run or resume live reference audits and score the selected benchmarks."""
    extra = ["--workers", str(workers)]
    if limit:
        extra.extend(["--limit", str(limit)])
    if retry_errors:
        extra.append("--retry-errors")
    if verbose:
        extra.append("--verbose")
    _benchmark_harness(context, "run", name, split, root, extra)


@task(positional=["name"], help={**BENCHMARK_HELP, "split": SPLIT_HELP})
def score(context, name, split="", root=""):
    """Rescore saved predictions without contacting metadata providers."""
    _benchmark_harness(context, "score", name, split, root)


@task(help={"root": BENCHMARK_HELP["root"]})
def verify(context, root=""):
    """Verify every benchmark and export baseline results after full completion."""
    _benchmark_python(context, "scripts.check_baseline", [], root)
