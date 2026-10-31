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


def _field_words(value):
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("{", "").replace("}", "")
    text = text.replace("‐", "-").replace("‑", "-")
    return tuple(re.findall(r"\w+(?:-\w+)*", text))


def equivalent_text(actual, expected, fragments):
    variants = {str(actual)}
    for left, right in zip(fragments, fragments[1:], strict=False):
        before = re.search(r"(\w+)-$", left["text"].rstrip())
        after = re.match(r"([a-zà-öø-ÿ]\w*)", right["text"].lstrip())
        if before and after:
            joined = before[1] + "-" + after[1]
            variants.update(value.replace(joined, before[1] + after[1]) for value in list(variants))
            if len(variants) > 64:
                raise ValueError("Too many independent oracle wrap variants")
    return any(_field_words(value) == _field_words(expected) for value in variants)


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
    value = codecs.decode(re.sub(r"\\([{}])", r"\1", "".join(output)), "ulatex")
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
    source = case.get("source_expectation", {})
    required = [dict(check) for check in source.get("field_checks", [])]
    required.extend(
        {"field": field, "results": [result]}
        for field, result in source.get("comparisons", {}).items()
    )
    required.extend(
        {"field": field, "results": [result]}
        for field, result in source.get("direct_comparisons", {}).items()
    )
    for check in required:
        if family in INITIAL_FAMILIES and check["field"] == "authors":
            check["results"] = [
                "unknown" if result in {"match", "partial_match"} else result
                for result in check["results"]
            ]
    if family in INITIAL_FAMILIES and case["citation_key"] == "adv_match_same_initial_impostor":
        required = [check for check in required if check["field"] != "authors"]
    if case["citation_key"] == "adv_match_literal_prefix_collision":
        required = [check for check in required if check["field"] != "authors"]
    if case["citation_key"] == "case_openreview_accepted_direct":
        for check in required:
            check["source"] = "openreview"
    return required


def required_issues(case, visibility):
    issue = case.get("source_expectation", {}).get("required_issue")
    if not issue:
        return []
    mutation = case.get("mutation") or {}
    changed = mutation.get("fields", mutation.get("set", {}))
    if case["citation_key"] == "adv_provider_shadowed_version_pin":
        changed = {key: value for key, value in changed.items() if key == "url"}
    if not any(visibility.get(field) in {"text", "annotation_only"} for field in changed):
        return []
    return [issue]


def _locator_visible(field, visibility):
    related = {
        "arxiv": ("eprint", "arxiv", "url", "journal"),
        "doi": ("doi", "url"),
        "pmlr": ("pmlr", "url"),
        "jmlr": ("jmlr", "url"),
        "acl": ("acl", "anthology_id", "url"),
        "openreview": ("openreview", "forum", "url"),
    }
    return any(
        visibility.get(name) in {"text", "annotation_only"} for name in related.get(field, (field,))
    )


def expected_statuses(case, family, visibility):
    source = case.get("source_expectation", {})
    status = source.get("reference_status")
    if case["citation_key"] == "case_openreview_accepted_direct":
        return ["Needs review"]  # Unlinked arXiv and accepted publication are both authoritative.
    if case["citation_key"] == "adv_match_literal_prefix_collision":
        return ["Needs review"] if family in INITIAL_FAMILIES else ["Partial match"]
    if source.get("required_issue") and not required_issues(case, visibility):
        if any(record.startswith("pal_") for record in case["canonical_records"]):
            return ["Needs review"]
        return ["Needs review"] if family in INITIAL_FAMILIES else ["Correct"]
    if status is None:
        statuses = source.get("acceptable_statuses")
        if statuses == ["Correct"] and family in INITIAL_FAMILIES:
            return ["Needs review"]
        return statuses or []
    if status in {"Correct", "Partial match"} and family in INITIAL_FAMILIES:
        return ["Needs review"]
    erased = _erased_mismatch_status(source, status, family, visibility)
    if erased:
        return erased
    if status == "Unresolved":
        return ["Unresolved", "Needs review"]
    return [status]


def _erased_mismatch_status(source, status, family, visibility):
    if status == "Invalid":
        mismatches = [
            field for field, result in source.get("comparisons", {}).items() if result == "mismatch"
        ]
        if mismatches and all(
            field in {"arxiv", "doi"} and not _locator_visible(field, visibility)
            for field in mismatches
        ):
            return ["Needs review"] if family in INITIAL_FAMILIES else ["Correct"]
    return None


def occurrence_classification(text, family):
    # A visible unknown marker or printed hanging label is still a reference occurrence.
    return "text" if text.strip() or family in NUMBERED_FAMILIES | {"ijcai"} else "omitted"


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
        "classification": occurrence_classification(text, family),
        "author_presentation": "initials" if family in INITIAL_FAMILIES else "full",
    }


def annotate_project(cell, truth):
    from pypdf import PdfReader

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
        "pages": len(PdfReader(project / "main.pdf").pages),
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
                "expected_statuses": expected_statuses(case, project["family"], visibility),
                "required_issues": required_issues(case, visibility),
                "canonical_records": case["canonical_records"],
                "classification": "omitted" if row.get("o") else "text",
            }
        )
    return expanded
