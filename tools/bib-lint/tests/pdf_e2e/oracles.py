"""Rendering oracles from frozen source facts and the native TeX renderer, never product output."""

import codecs
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import latexcodec  # noqa: F401 -- independent TeX text decoding, not product normalization

from bib_lint.parser import parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pdf"
RELEVANT_FIELDS = (
    "title",
    "year",
    "journal",
    "booktitle",
    "doi",
    "url",
    "eprint",
    "arxiv",
    "pmlr",
    "jmlr",
    "acl",
    "anthology_id",
    "openreview",
    "forum",
)
INITIAL_FAMILIES = {"icml", "aaai", "aistats", "eccv"}
NUMBERED_FAMILIES = {"cvpr", "eccv"}


def normalized(value):
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in text if character.isalnum())


def _group(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        return "", start
    depth, end = 1, start + 1
    while end < len(text) and depth:
        if text[end] == "\\":
            end += 2
            continue
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start + 1 : end - 1], end


def rendered_text(text):
    """Expand only presentation macros in the already-generated bibliography body."""
    output, targets, index = [], [], 0
    while index < len(text):
        match = re.match(r"\\([A-Za-z]+)", text[index:])
        if not match:
            output.append(text[index])
            index += 1
            continue
        name = match[1]
        index += len(match[0])
        if name == "href":
            target, index = _group(text, index)
            label, index = _group(text, index)
            targets.append(target)
            output.append(rendered_text(label)[0])
        elif name in {"url", "doi", "emph", "textit", "texttt", "textrm", "natexlab"}:
            argument, index = _group(text, index)
            if name == "doi":
                targets.append("https://doi.org/" + argument)
                output.append("doi: ")
            output.append(rendered_text(argument)[0])
        elif name == "penalty":
            digits = re.match(r"\s*-?\d+", text[index:])
            index += len(digits[0]) if digits else 0
        elif name in {"newblock", "allowbreak", "relax", "em", "bgroup", "egroup"}:
            output.append(" ")
        else:
            output.append("\\" + name)
    value = codecs.decode("".join(output), "ulatex")
    return " ".join(value.replace("{", "").replace("}", "").replace("~", " ").split()), targets


def bibliography_bodies(text):
    headers = list(re.finditer(r"\\bibitem(?:\[[\s\S]*?\])?\s*\{([^}]+)\}", text))
    result = []
    for index, header in enumerate(headers):
        end = (
            headers[index + 1].start()
            if index + 1 < len(headers)
            else text.find(r"\end{thebibliography}", header.end())
        )
        result.append((header[1], text[header.end() : end]))
    return result


def _person(person, initials):
    given = " ".join((*person.first, *person.middle))
    if initials:
        given = " ".join(token[0] + "." for token in given.split() if token)
    return {
        "given": rendered_text(given)[0],
        "family": rendered_text(" ".join((*person.prelast, *person.last)))[0],
        "suffix": rendered_text(" ".join(person.lineage))[0],
        "kind": person.kind,
    }


def _required_checks(case, family):
    checks = case.get("source_expectation", {}).get("field_checks", [])
    required = [
        check for check in checks if check["field"] in {"authors", "year", "title", "venue"}
    ]
    if family in INITIAL_FAMILIES and case["citation_key"] == "adv_match_same_initial_impostor":
        required = [check for check in required if check["field"] != "authors"]
    if case["citation_key"] == "adv_match_literal_prefix_collision":
        required = [check for check in required if check["field"] != "authors"]
    return required


def _case_expectation(case, entry, family, body):
    text, targets = rendered_text(body)
    visibility, expected = {}, {}
    folded = normalized(text)
    for field in RELEVANT_FIELDS:
        value = entry.fields.get(field)
        if not value:
            continue
        plain = rendered_text(value)[0]
        visible = bool(normalized(plain)) and normalized(plain) in folded
        annotated = any(value == target or value in target for target in targets)
        visibility[field] = "text" if visible else "annotation_only" if annotated else "omitted"
        if visible:
            expected[field] = plain
    authors = [
        _person(person, family in INITIAL_FAMILIES) for person in entry.persons.get("author", ())
    ]
    required = _required_checks(case, family)
    return {
        "source_key": entry.key,
        "case_id": case["id"],
        "visibility": visibility,
        "expected_fields": expected,
        "expected_authors": authors,
        "rendered_text": text,
        "annotation_targets": targets,
        "required_checks": required,
        "canonical_records": case["canonical_records"],
        "classification": "text" if normalized(text) or family in NUMBERED_FAMILIES else "omitted",
        "author_presentation": "initials" if family in INITIAL_FAMILIES else "full",
    }


def annotate_project(cell, truth):
    project = Path(cell["project"])
    recipe = json.loads((project / "recipe.json").read_text())
    source = FIXTURES / "corpora" / recipe["corpus"]["path"]
    entries = parse_file(source).entries
    cases = {
        case["citation_key"]: case
        for case in truth["cases"]
        if case["corpus"] == recipe["corpus"]["id"]
    }
    inverse = {build_key: source_key for source_key, build_key in recipe["key_map"].items()}
    bodies = bibliography_bodies((project / "main.bbl").read_text())
    annotations = []
    for build_key, body in bodies:
        key = inverse[build_key]
        annotations.append(
            _case_expectation(cases[key], entries[key], recipe["venue"]["family"], body)
        )
    return {
        "venue": cell["venue"],
        "family": recipe["venue"]["family"],
        "corpus": cell["corpus"],
        "pdf_sha256": hashlib.sha256((project / "main.pdf").read_bytes()).hexdigest(),
        "selection": recipe["selection"],
        "cases": annotations,
    }


def freeze_oracles(ledger):
    truth = json.loads((FIXTURES / "truth.json").read_text())
    cells = ledger["renderable_builds"] + ledger["renderable_counterparts"]
    return {
        "schema_version": 1,
        "basis": "Frozen citation facts and native bibliography bodies; reviewed style expansion. "
        "No product extractor, matcher, audit verdict, or retrieved correction defines gold.",
        "build_policy_sha256": hashlib.sha256(
            (FIXTURES / "build_cases.json").read_bytes()
        ).hexdigest(),
        "build_negatives": [
            {k: v for k, v in case.items() if k != "project"}
            for case in ledger["isolated_build_negatives"]
        ],
        "projects": [annotate_project(cell, truth) for cell in cells],
    }


def compact_oracles(gold):
    """Track source bindings/visibility, not another copy of every rendered citation."""
    compact = dict(gold)
    compact["case_columns"] = {
        "k": "source citation key",
        "t": "fields printed as text",
        "a": "fields retained only in annotations",
        "o": "empty author-year occurrence omitted from the rendering",
    }
    compact["projects"] = []
    for project in gold["projects"]:
        result = {key: value for key, value in project.items() if key not in {"cases", "selection"}}
        result["selection"] = {
            key: value for key, value in project["selection"].items() if key != "included"
        }
        result["cases"] = []
        for case in project["cases"]:
            row = {
                "k": case["source_key"],
                "t": list(case["expected_fields"]),
                "a": [
                    key for key, value in case["visibility"].items() if value == "annotation_only"
                ],
            }
            if case["classification"] == "omitted":
                row["o"] = True
            result["cases"].append(row)
        compact["projects"].append(result)
    return compact


def expand_project(project, truth):
    source = FIXTURES / "corpora" / (project["corpus"] + ".bib")
    entries = parse_file(source).entries
    cases = {
        case["citation_key"]: case for case in truth["cases"] if case["corpus"] == project["corpus"]
    }
    expanded = dict(project)
    expanded["cases"] = []
    for row in project["cases"]:
        entry, case = entries[row["k"]], cases[row["k"]]
        visibility = {
            field: "text"
            if field in row["t"]
            else "annotation_only"
            if field in row["a"]
            else "omitted"
            for field in RELEVANT_FIELDS
            if entry.fields.get(field)
        }
        expanded["cases"].append(
            {
                "source_key": row["k"],
                "case_id": case["id"],
                "visibility": visibility,
                "expected_fields": {
                    field: rendered_text(entry.fields[field])[0] for field in row["t"]
                },
                "expected_authors": [
                    _person(person, project["family"] in INITIAL_FAMILIES)
                    for person in entry.persons.get("author", ())
                ],
                "required_checks": _required_checks(case, project["family"]),
                "canonical_records": case["canonical_records"],
                "classification": "omitted" if row.get("o") else "text",
            }
        )
    return expanded
