"""Acquire and load official releases; retain every published example."""

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from bib_lint.storage import write_json
from evaluation.benchmarks.common import digest

HALLMARK_REVISION = "f774fa40675daa83eca6201637a94c4536b7bb3e"
HALLMARK_BASE = f"https://raw.githubusercontent.com/rpatrik96/hallmark/{HALLMARK_REVISION}"
ZENODO_RECORD = "23236264"
GPTZERO_SHEET = "14hIuCK7HCnGhdCuxfwp1wIYbbHMn-K3FNvY9NgWGW0Y"
BENCHMARKS = {
    "hallmark": {
        "release": f"v1.2.3@{HALLMARK_REVISION}",
        "source": "https://github.com/rpatrik96/hallmark",
        "evaluation": "official_python_evaluator",
        "license": "MIT",
        "splits": ["dev_public", "test_public", "stress_test"],
    },
    "zenodo": {
        "release": f"1.1.0@{ZENODO_RECORD}",
        "source": f"https://zenodo.org/records/{ZENODO_RECORD}",
        "evaluation": "documented_binary_protocol_no_released_scorer",
        "license": "CC-BY-4.0",
        "splits": ["all"],
    },
    "gptzero": {
        "release": "public_neurips2025_sheet_snapshot",
        "source": "https://gptzero.me/news/neurips/",
        "evaluation": "positive_only_collection_no_official_scorer",
        "license": "No explicit dataset license found; local evaluation only",
        "splits": ["all"],
    },
    "hallucitation": {
        "release": "arxiv:2601.18724v1",
        "source": "https://arxiv.org/html/2601.18724v1#A2",
        "evaluation": "published_positive_only_appendix_no_official_scorer",
        "license": "Published paper; locally extracted appendix for research evaluation",
        "splits": ["all"],
    },
}


@dataclass(frozen=True)
class Case:
    id: str
    benchmark: str
    split: str
    original: dict
    issue: bool
    fields: dict | None = None
    bibtex_type: str = "misc"
    raw_reference: str | None = None


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_snapshot(folder):
    manifest = json.loads((folder / "snapshot.json").read_text())
    for name, info in manifest["files"].items():
        if digest((folder / name).read_bytes()) != info["sha256"]:
            raise ValueError(f"Official snapshot changed: {folder / name}")
    return manifest


def prepare(name, root, client=None):
    folder = Path(root) / "sources" / name
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "snapshot.json").exists():
        return verify_snapshot(folder)
    spec = BENCHMARKS[name]
    manifest = {
        **spec,
        "benchmark": name,
        "files": {},
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    urls = _source_urls(name, spec)
    own_client = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        for filename, url in urls.items():
            response = client.get(url)
            response.raise_for_status()
            _validate_download(name, url, filename, response)
            path = folder / filename
            if path.exists() and path.read_bytes() != response.content:
                raise ValueError(f"Refusing to replace an existing snapshot: {path}")
            path.write_bytes(response.content)
            manifest["files"][filename] = {"url": url, "sha256": digest(response.content)}
            if name == "hallucitation":
                # Parse before declaring acquisition ready; HTML error pages or
                # partial conversions must not masquerade as a usable collection.
                load_appendix(response.content)
    finally:
        if own_client:
            client.close()
    manifest["status"] = "ready"
    write_json(folder / "snapshot.json", manifest)
    return manifest


def load_appendix(content):
    soup = BeautifulSoup(content, "html.parser")
    tables = [t for t in soup.find_all("table") if "Example of HalluCitation" in t.get_text()]
    if len(tables) != 1:
        raise ValueError("Expected exactly one official HalluCitation appendix table")
    rows = []
    for tr in tables[0].find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        values = [c.get_text(" ", strip=True) for c in cells]
        if len(values) != 5:
            continue
        number = re.fullmatch(r"(?:\\endlastfoot\s*)?(\d+)", values[0])
        if not number:
            continue
        if not values[2] or not values[4]:
            raise ValueError("Empty paper ID or reference in HalluCitation appendix")
        rows.append(
            {
                "row_number": int(number[1]),
                "event_id": values[1],
                "paper_id": values[2],
                "paper_citation": values[3],
                "reference": values[4],
                # The published row 226 contains two distinct examples in one
                # cell. Split at its explicit second citation, retaining the
                # original cell rather than losing that reference.
                "references": re.split(r"(?<=\.)\s+(?=X\. Du et al\. 2022b\. Grit2:)", values[4])
                if int(number[1]) == 226
                else [values[4]],
                "original_cells": values,
                "row_html_sha256": digest(str(tr).encode()),
            }
        )
    # The pinned published version has exactly 295 numbered examples. This guards
    # against quietly losing a row to HTML conversion or a changed table format.
    if [r["row_number"] for r in rows] != list(range(1, 296)):
        raise ValueError("Hallucitation v1 appendix must retain rows 1 through 295 in order")
    return rows


def load_cases(name, split, root):
    folder = Path(root) / "sources" / name
    verify_snapshot(folder)
    if split not in BENCHMARKS[name]["splits"]:
        raise ValueError(f"Unknown split {split!r} for {name}")
    if name == "hallucitation":
        return _appendix_cases(folder, name, split)
    if name == "hallmark":
        rows = read_jsonl(folder / f"{split}.jsonl")
        # The official loader excludes canaries, and nothing else. Do not deduplicate,
        # drop malformed TeX, change labels, or repair fields.
        return [
            Case(
                row["bibtex_key"],
                name,
                split,
                row,
                row["label"] == "HALLUCINATED",
                row["fields"],
                row["bibtex_type"],
            )
            for row in rows
            if not row["bibtex_key"].startswith("__canary__")
        ]
    filename = "manual_reference_verification_dataset.csv" if name == "zenodo" else "references.csv"
    rows = list(csv.DictReader(io.StringIO((folder / filename).read_bytes().decode("utf-8-sig"))))
    required = (
        {"document_id", "reference_number", "manual_label", "reference"}
        if name == "zenodo"
        else {"Published Paper", "Example of Verified Hallucination"}
    )
    if not rows or any(not required <= row.keys() for row in rows):
        raise ValueError(f"Empty dataset or missing official columns: {filename}")
    if name == "zenodo":
        for row in rows:
            if row["manual_label"] not in {"verified", "problematic"}:
                raise ValueError(f"Unknown manual label: {row['manual_label']}")
        return [
            Case(
                f"{r['document_id']}_{r['reference_number']}",
                name,
                split,
                r,
                r["manual_label"] == "problematic",
                raw_reference=r["reference"],
            )
            for r in rows
        ]
    return [
        Case(
            f"gptzero_{i:03d}",
            name,
            split,
            row,
            True,
            raw_reference=row["Example of Verified Hallucination"],
        )
        for i, row in enumerate(rows, 1)
    ]


def _source_urls(name, spec):
    urls = {}
    if name == "hallmark":
        urls = {
            f"{split}.jsonl": f"{HALLMARK_BASE}/data/v1.2/{split}.jsonl" for split in spec["splits"]
        }
        urls.update(
            {
                "LICENSE": f"{HALLMARK_BASE}/LICENSE",
                "README.md": f"{HALLMARK_BASE}/README.md",
                "metadata.json": f"{HALLMARK_BASE}/data/v1.2/metadata.json",
            }
        )
    elif name == "zenodo":
        base = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files"
        urls = {
            filename: f"{base}/{filename}/content"
            for filename in ["manual_reference_verification_dataset.csv", "README.md"]
        }
    elif name == "gptzero":
        urls = {
            "references.csv": f"https://docs.google.com/spreadsheets/d/{GPTZERO_SHEET}"
            "/export?format=csv&gid=0"
        }
    elif name == "hallucitation":
        urls = {"appendix.html": "https://arxiv.org/html/2601.18724v1"}
    return urls


def _validate_download(name, url, filename, response):
    if name != "hallucitation" and "text/html" in response.headers.get("content-type", ""):
        raise ValueError(f"Expected data, received HTML from {url}")
    if filename.endswith(".jsonl"):
        for line in response.text.splitlines():
            json.loads(line)


def _appendix_cases(folder, name, split):
    cases = []
    for row in load_appendix((folder / "appendix.html").read_bytes()):
        for index, raw in enumerate(row["references"], 1):
            key = f"hallucitation_{row['row_number']:03d}"
            if len(row["references"]) > 1:
                key += f"_r{index}"
            cases.append(
                Case(key, name, split, {**row, "reference_index": index}, True, raw_reference=raw)
            )
    return cases
