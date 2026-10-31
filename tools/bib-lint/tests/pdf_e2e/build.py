"""Validate frozen inputs for real LaTeX-to-PDF acceptance tests."""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from bib_lint.parser import parse_file
from pdf_e2e.assets import prepare_asset
from pdf_e2e.compiler import compile_project
from pdf_e2e.matrix import complete_matrix
from pdf_e2e.projects import create_project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pdf"

CACHE = FIXTURES.parents[4] / ".local/pdf-e2e/assets"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def checked_bytes(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError(f"Unexpected checksum: {path}")
    return raw


def check_inputs(fixtures: Path = FIXTURES) -> dict:
    manifest = read_json(fixtures / "corpora/manifest.json")
    truth_pin = manifest["truth"]
    truth = json.loads(checked_bytes(fixtures / "corpora" / truth_pin["path"], truth_pin["sha256"]))
    bindings = []
    for corpus in manifest["corpora"]:
        path = fixtures / "corpora" / corpus["path"]
        raw = checked_bytes(path, corpus["sha256"])
        entries = parse_file(path).entries
        inventory = (len(raw), list(entries), dict(Counter(e.type for e in entries.values())))
        expected = (corpus["bytes"], corpus["entry_keys"], corpus["entry_types"])
        if inventory != expected or len(entries) != corpus["entry_count"]:
            raise ValueError(f"Unexpected corpus inventory: {path}")
        bindings.extend((corpus["id"], key) for key in entries)
    cases = truth["cases"]
    actual = [(case["corpus"], case["citation_key"]) for case in cases]
    if Counter(bindings) != Counter(actual):
        raise ValueError("Case inventory must cover every corpus entry exactly once")
    canonical = truth["canonical_records"]
    for case in cases:
        if any(record not in canonical for record in case["canonical_records"]):
            raise ValueError(f"Unknown canonical record: {case['id']}")
    return {"corpora": len(manifest["corpora"]), "entries": len(bindings), "cases": len(cases)}


def check_templates(fixtures: Path = FIXTURES) -> dict:
    manifest = read_json(fixtures / "templates.json")
    venues, assets = manifest["venues"], manifest["assets"]
    if len({v["id"] for v in venues}) != manifest["required_venue_count"]:
        raise ValueError("Unexpected required venue inventory")
    for venue in venues:
        asset = assets[venue["asset"]]
        pin = asset.get("sha256")
        if not isinstance(pin, str) or len(pin) != 64 or not asset["files"]:
            raise ValueError(f"Unpinned template asset: {venue['asset']}")
        if not venue["bibliography"]:
            raise ValueError(f"Unpinned bibliography recipe: {venue['id']}")
    builds = len(venues) * len(read_json(fixtures / "corpora/manifest.json")["corpora"])
    if builds != manifest["required_baseline_builds"]:
        raise ValueError("Unexpected baseline build inventory")
    return {"venues": len(venues), "assets": len(assets), "baseline_builds": builds}


def compile_baseline(cache: Path, output: Path) -> dict:
    manifest = read_json(FIXTURES / "templates.json")
    corpora = read_json(FIXTURES / "corpora/manifest.json")["corpora"]
    results = []
    for venue in manifest["venues"]:
        asset = manifest["assets"][venue["asset"]]
        for corpus in corpora:
            cell = {"venue": venue["id"], "corpus": corpus["id"]}
            try:
                asset_dir = cache / asset["sha256"]
                for member in asset["files"]:
                    checked_bytes(asset_dir / member["path"], member["sha256"])
                project = create_project(venue, corpus, asset_dir, FIXTURES, output)
                cell["project"] = str(project)
                receipt = compile_project(project)
                cell.update(status="compiled", pdf_sha256=receipt["pdf_sha256"])
            except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                cell.update(status="failed", error=str(error))
            results.append(cell)
            print(
                f"{cell['venue']}/{cell['corpus']}: {cell['status']}", file=sys.stderr, flush=True
            )
    result = {
        "matrix": "baseline",
        "required_builds": manifest["required_baseline_builds"],
        "compiled": sum(cell["status"] == "compiled" for cell in results),
        "builds": results,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "baseline.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check-inputs", action="store_true")
    actions.add_argument("--prepare-assets", action="store_true")
    actions.add_argument("--compile", action="store_true")
    parser.add_argument("--matrix", choices=["baseline"], default="baseline")
    parser.add_argument("--output", type=Path, default=CACHE.parent / "projects")
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    result = {"inputs": check_inputs(), "templates": check_templates()}
    if args.prepare_assets:
        manifest = read_json(FIXTURES / "templates.json")
        result["prepared_assets"] = {
            name: str(prepare_asset(name, pin, args.cache))
            for name, pin in manifest["assets"].items()
        }
    if args.compile:
        baseline = compile_baseline(args.cache, args.output)
        result["compilation"] = complete_matrix(
            baseline,
            read_json(FIXTURES / "templates.json"),
            read_json(FIXTURES / "corpora/manifest.json")["corpora"],
            args.cache,
            args.output,
        )
    print(json.dumps(result))
    if args.compile and not result["compilation"]["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
