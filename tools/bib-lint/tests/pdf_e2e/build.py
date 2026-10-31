"""Validate frozen inputs for real LaTeX-to-PDF acceptance tests."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from bib_lint.parser import parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pdf"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-inputs", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps({"inputs": check_inputs(), "templates": check_templates()}))


if __name__ == "__main__":
    main()
