"""Prepare, run, resume and score official benchmarks with bib-lint."""

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path

import httpx

import bib_lint
from bib_lint.audit import run_audit
from bib_lint.storage import report_lock, write_json
from bib_lint.verification.cache import ResponseCache
from bib_lint.verification.http import MetadataClient
from bib_lint.verification.providers import METHODS
from evaluation.benchmarks.conversion import CONVERSION_VERSION, make_report
from evaluation.benchmarks.execution import HostPacer, PacedMetadataClient
from evaluation.benchmarks.scoring import (
    MAPPING_VERSION,
    check_official_evaluator,
    prediction_from_report,
    score,
    unavailable_prediction,
)
from evaluation.benchmarks.sources import BENCHMARKS, load_cases, prepare, verify_snapshot

DEFAULT_ROOT = Path(__file__).parent / ".artifacts"


def tool_identity():
    package = Path(bib_lint.__file__).parent
    files = {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob("*.py"))
    }
    harness_files = {
        str(p.relative_to(Path(__file__).parent)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(__file__).parent.rglob("*.py"))
        if ".artifacts" not in p.parts
    }
    return json.loads(
        json.dumps(
            {
                "tool_source": files,
                "harness_source": harness_files,
                "conversion_version": CONVERSION_VERSION,
                "mapping_version": MAPPING_VERSION,
                "providers": [p.descriptor.serialize() for p in METHODS.values()],
            }
        )
    )


def write_predictions(path, predictions):
    # Whole-file atomic checkpoint; interrupted runs keep all completed cases.
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions))
    temporary.replace(path)


def read_predictions(folder):
    path = folder / "predictions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def run_split(
    name,
    split,
    root,
    *,
    limit=None,
    retry_errors=False,
    verbose=False,
    workers=1,
    audit=run_audit,
    client=None,
):
    if workers < 1 or (workers > 1 and client is not None):
        raise ValueError("Positive workers required; an injected client supports one worker only")
    cases = load_cases(name, split, root)
    if name == "hallmark":
        check_official_evaluator()
    folder = root / "runs" / name / split
    folder.mkdir(parents=True, exist_ok=True)
    snapshot = verify_snapshot(root / "sources" / name)
    configuration = {
        "identity": tool_identity(),
        "source_files": snapshot["files"],
        "benchmark": name,
        "split": split,
        "execution": {"workers": workers, "shared_host_pacing": True},
    }
    config_path = folder / "run-config.json"
    if config_path.exists() and json.loads(config_path.read_text()) != configuration:
        raise ValueError(f"Tool, parser or dataset changed; use a fresh --root: {folder}")
    write_json(config_path, configuration)
    predictions = read_predictions(folder)
    by_id = {p["id"]: p for p in predictions}
    if len(by_id) != len(predictions) or set(by_id) - {c.id for c in cases}:
        raise ValueError("Invalid saved prediction IDs")
    selected = cases if limit is None else cases[:limit]
    pacer = HostPacer()
    stopped = threading.Event()

    execute = _case_executor(
        folder, name, split, selected, stopped, verbose, client, pacer, audit, root, retry_errors
    )

    def save(case, prediction):
        by_id[case.id] = prediction
        predictions = [by_id[c.id] for c in cases if c.id in by_id]
        write_predictions(folder / "predictions.jsonl", predictions)
        write_json(
            folder / "progress.json",
            {
                "updated_at": datetime.now(UTC).isoformat(),
                "official_cases": len(cases),
                "attempted": len(by_id),
                "workers": workers,
                "statuses": dict(Counter(p["status"] for p in by_id.values())),
            },
        )
        print(
            f"[{name}/{split}] completed {len(by_id)}/{len(cases)} {case.id}: "
            f"{prediction['status']}",
            file=sys.stderr,
            flush=True,
        )

    pending = [
        (i, c)
        for i, c in enumerate(selected, 1)
        if not by_id.get(c.id)
        or (retry_errors and (not by_id[c.id]["evaluated"] or by_id[c.id]["source_errors"]))
    ]
    if workers == 1:
        for index, case in pending:
            save(case, execute(case, index))
    else:
        _run_parallel(workers, pending, execute, save, stopped)
    predictions = [by_id[c.id] for c in cases if c.id in by_id]
    write_json(
        folder / "run-status.json",
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "official_cases": len(cases),
            "attempted": len(by_id),
            "limited_run": limit is not None,
            "complete": len(by_id) == len(cases),
            "statuses": dict(Counter(p["status"] for p in by_id.values())),
        },
    )
    return score(name, split, cases, predictions, folder, root / "sources" / name)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=["list", "prepare", "run", "score"])
    result.add_argument("--benchmark", choices=["all", *BENCHMARKS], default="all")
    result.add_argument("--split", help="One official split; requires a single benchmark")
    result.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    result.add_argument(
        "--limit", type=int, help="Smoke run: first N cases per split; explicitly partial"
    )
    result.add_argument(
        "--retry-errors", action="store_true", help="Retry failures and source errors on resume"
    )
    result.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent cases with shared host pacing (default 8)",
    )
    result.add_argument("--verbose", action="store_true", help="Show provider progress on stderr")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.limit is not None and (args.limit <= 0 or args.command != "run"):
        raise SystemExit("--limit must be positive and is only valid for run")
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    if args.split and args.benchmark == "all":
        raise SystemExit("--split requires a single --benchmark")
    if args.command == "list":
        print(json.dumps(BENCHMARKS, indent=2))
        return 0
    root = args.root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    names = (
        ["zenodo", "gptzero", "hallucitation", "hallmark"]
        if args.benchmark == "all"
        else [args.benchmark]
    )
    results, failed = {}, False
    with report_lock(root / "harness.json"):
        for name in names:
            try:
                value, benchmark_failed = _benchmark_command(args, name, root)
                results[name] = value
                failed = failed or benchmark_failed
            except (ValueError, OSError, httpx.HTTPError) as exc:
                results[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                failed = True
    write_json(root / f"{args.command}-summary.json", results)
    print(json.dumps(results, indent=2))
    return 2 if failed else 0


def _case_executor(
    folder, name, split, selected, stopped, verbose, client, pacer, audit, root, retry_errors
):
    def execute(case, index):
        case_folder = folder / "cases" / hashlib.sha256(case.id.encode()).hexdigest()[:24]
        case_folder.mkdir(parents=True, exist_ok=True)
        print(
            f"[{name}/{split}] {index}/{len(selected)} {case.id}: starting",
            file=sys.stderr,
            flush=True,
        )

        def progress(message):
            if stopped.is_set():
                raise KeyboardInterrupt
            with (case_folder / "progress.log").open("a") as handle:
                handle.write(f"{datetime.now(UTC).isoformat()} {message}\n")
            if verbose:
                print(message, file=sys.stderr, flush=True)

        start = time.monotonic()
        stage = "conversion"
        task_client = None
        try:
            report, conversion = make_report(case)
            stage = "storage"
            write_json(case_folder / "conversion.json", conversion)
            input_path = case_folder / "input.json"
            write_json(input_path, report)
            stage = "client_setup"
            task_client = client or PacedMetadataClient(case_folder / "audit" / "cache", pacer)
            if isinstance(task_client, MetadataClient):
                task_client.cache_dir = case_folder / "audit" / "cache"
                task_client.cache = ResponseCache(task_client.cache_dir)
                task_client.refresh = retry_errors
            stage = "bib_lint"
            _, report, _ = audit(
                input_path,
                output=case_folder / "audit",
                client=task_client,
                progress=progress,
                refresh=retry_errors,
            )
            stage = "export"
            prediction = prediction_from_report(report, time.monotonic() - start)
            if prediction["id"] != case.id:
                raise ValueError("Audit returned a different benchmark reference")
        except Exception as exc:
            prediction = unavailable_prediction(case.id, f"{type(exc).__name__}: {exc}")
            prediction["failure_stage"] = stage
            write_json(
                case_folder / ("tool-error.json" if stage == "bib_lint" else "input-error.json"),
                {
                    "id": case.id,
                    "raw_reference": case.raw_reference,
                    "error": str(exc),
                    "stage": stage,
                },
            )
        finally:
            if client is None and task_client is not None:
                task_client.close()
        prediction["case_dir"] = str(case_folder.relative_to(root))
        return prediction

    return execute


def _run_parallel(workers, pending, execute, save, stopped):
    executor = ThreadPoolExecutor(max_workers=workers)
    waiting = iter(pending)
    futures = {}

    def submit_next():
        item = next(waiting, None)
        if item:
            index, case = item
            futures[executor.submit(execute, case, index)] = case

    try:
        for _ in range(workers):
            submit_next()
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                save(futures.pop(future), future.result())
                submit_next()
    finally:
        # Do not queue the whole corpus: Ctrl-C cancels pending work and
        # running audits stop at their next normal progress boundary.
        stopped.set()
        executor.shutdown(wait=True, cancel_futures=True)
        for future, case in futures.items():
            if future.done() and not future.cancelled() and future.exception() is None:
                save(case, future.result())


def _benchmark_command(args, name, root):
    results, failed = {}, False
    snapshot = (
        prepare(name, root)
        if args.command in {"prepare", "run"}
        else verify_snapshot(root / "sources" / name)
    )
    if snapshot["status"] == "unavailable":
        results[name] = snapshot
        failed = True
        return results[name], failed
    if args.command == "prepare":
        results[name] = snapshot
        return results[name], failed
    splits = [args.split] if args.split else BENCHMARKS[name]["splits"]
    results[name] = {}
    for split in splits:
        if args.command == "run":
            value = run_split(
                name,
                split,
                root,
                limit=args.limit,
                retry_errors=args.retry_errors,
                verbose=args.verbose,
                workers=args.workers,
            )
        else:
            cases = load_cases(name, split, root)
            folder = root / "runs" / name / split
            folder.mkdir(parents=True, exist_ok=True)
            value = score(
                name,
                split,
                cases,
                read_predictions(folder),
                folder,
                root / "sources" / name,
            )
        results[name][split] = value
        if not value["harness_ok"]:
            failed = True
    return results[name], failed


if __name__ == "__main__":
    raise SystemExit(main())
