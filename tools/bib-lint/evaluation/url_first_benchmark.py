"""Offline queue overhead and task-count comparison; no provider requests."""

import argparse
import json
import threading
from pathlib import Path
from time import perf_counter, sleep

from evaluation.provider_queues import ProviderQueues
from evaluation.url_first import run_entries

URLS = (
    "https://arxiv.org/abs/2401.12345",
    "https://proceedings.mlr.press/v235/example24a.html",
    "https://jmlr.org/papers/v25/24-001.html",
    "https://aclanthology.org/2024.acl-long.1/",
    "https://proceedings.neurips.cc/paper/2024/hash/abc-Abstract.html",
    "https://openreview.net/forum?id=Example",
)


def _measure(folder, entries, full_fanout, latency):
    folder.mkdir(parents=True, exist_ok=False)

    def lookup(entry, provider, phase):
        if latency:
            sleep(latency)
        return {"outcome": "resolved", "status": "synthetic", "key": entry["key"]}

    baseline_threads = threading.active_count()
    start = perf_counter()
    with ProviderQueues(folder, lookup) as queues:
        extra_threads = threading.active_count() - baseline_threads
        if full_fanout:
            futures = [
                queues.submit(entry, provider, "search")
                for entry in entries
                for provider in queues.providers
            ]
            for future in futures:
                future.get(blocking=True, timeout=60)
        else:
            run_entries(entries, queues)
    return {
        "submitted": queues.submitted,
        "wall_seconds": round(perf_counter() - start, 4),
        "extra_threads": extra_threads,
        "database_bytes": sum(path.stat().st_size for path in folder.glob("*.db*")),
    }


def benchmark(root, citations=100, latency=0):
    if citations < 1 or latency < 0:
        raise ValueError("Citations must be positive and latency nonnegative")
    entries = [
        {"key": f"reference-{i}", "fields": {"url": URLS[i % len(URLS)]}} for i in range(citations)
    ]
    return {
        "citations": citations,
        "simulated_lookup_seconds": latency,
        "url_first": _measure(root / "url-first", entries, False, latency),
        "all_sources": _measure(root / "all-sources", entries, True, latency),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Fresh artifact directory")
    parser.add_argument("--citations", type=int, default=100)
    parser.add_argument("--latency", type=float, default=0)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.root, args.citations, args.latency), indent=2))


if __name__ == "__main__":
    main()
