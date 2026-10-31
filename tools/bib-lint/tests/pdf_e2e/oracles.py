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
        after = re.match(r"([^\W\d_]\w*)", right["text"].lstrip())
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


def _expanded_tex(text):
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
            output.append(_expanded_tex(label)[0])
        elif name in {"url", "doi", "emph", "textit", "texttt", "textrm", "natexlab"}:
            argument, index = _group(text, index)
            if name == "doi":
                targets.append("https://doi.org/" + argument)
                output.append("doi: ")
            if name in {"url", "doi"}:
                argument = re.sub(r"(?<!\\)%", "\uf000", argument)
            output.append(_expanded_tex(argument)[0])
        elif name == "penalty":
            digits = re.match(r"\s*-?\d+", text[index:])
            index += len(digits[0]) if digits else 0
        elif name in {"newblock", "allowbreak", "relax", "em", "bgroup", "egroup"}:
            output.append(" ")
        else:
            output.append("\\" + name)
    return "".join(output), targets


def rendered_text(text):
    """Expand native presentation macros; locator macro percent signs are literal."""
    if re.match(r"(?:https?://|10\.)", text, re.I):
        text = re.sub(r"(?<!\\)%", "\uf000", text)
    expanded, targets = _expanded_tex(text)
    value = codecs.decode(re.sub(r"\\([{}])", r"\1", expanded), "ulatex").replace("\uf000", "%")
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


def printed_authors(authors, body):
    """Honor the native renderer's explicit count of unprinted trailing people."""
    count = re.search(r"\band\s+(\d+)\s+others\b", body)
    if not count:
        return authors
    shown = len(authors) - int(count[1])
    if shown < 1:
        raise ValueError("Native truncated author count exceeds the source list")
    return authors[:shown] + [{"given": "", "family": "others", "suffix": "", "kind": "others"}]


def author_structure_visible(authors):
    # Native styles erase protected-name groups and print arbitrary suffixes
    # with the same separators as distinct authors. A PDF cannot recover them.
    return not any(
        re.search(r"\band\b", author["given"])
        or author["suffix"].strip(".").casefold() not in {"", "jr", "sr", "ii", "iii", "iv"}
        for author in authors
    )


VENUE_MUTATIONS = {
    "adv_consensus_shadowed_booktitle": "booktitle",
    "adv_consensus_shadowed_journal": "journal",
    "adv_consensus_arxiv_impostor_venue": "journal",
    "adv_provider_venue_masquerade": "booktitle",
}


def visible_checks(case, family, visibility):
    changed_venue = VENUE_MUTATIONS.get(case["citation_key"])
    erased = changed_venue and visibility.get(changed_venue) not in {"text", "annotation_only"}
    return [
        check
        for check in _required_checks(case, family)
        if not (erased and check["field"] == "venue")
    ]


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
    override = _rendering_status(case, family, visibility)
    if override:
        return override
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


def _rendering_status(case, family, visibility):
    source = case.get("source_expectation", {})
    if case["citation_key"] == "case_openreview_accepted_direct":
        return ["Needs review"]  # Unlinked arXiv and accepted publication are both authoritative.
    if case["citation_key"] == "adv_match_literal_prefix_collision":
        return ["Partial match"]  # Literal names retain their full given names in initial styles.
    if source.get("required_issue") and not required_issues(case, visibility):
        if any(record.startswith("pal_") for record in case["canonical_records"]):
            return ["Needs review"]
        return ["Needs review"] if family in INITIAL_FAMILIES else ["Correct"]
    changed_venue = VENUE_MUTATIONS.get(case["citation_key"])
    if changed_venue and visibility.get(changed_venue) not in {"text", "annotation_only"}:
        return ["Needs review"] if family in INITIAL_FAMILIES else ["Correct"]
    return None


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


def typeset_locator_issues(targets, actual_uris):
    def comparable(value):
        return re.sub(r"\\+([%{}])", r"\1", value).casefold()

    actual = {comparable(uri) for uri in actual_uris}
    bad = any(
        comparable(target) in actual
        and re.match(r"https?://doi\.org/https?://(?:dx\.)?doi\.org/", comparable(target))
        for target in targets
    )
    return [{"field": "doi", "code": "typeset_nested_doi_url"}] if bad else []


def _case_expectation(case, entry, family, body, actual_uris=()):
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
    authors = printed_authors(
        [_person(person, family in INITIAL_FAMILIES) for person in entry.persons.get("author", ())],
        text,
    )
    required = _required_checks(case, family)
    return {
        "source_key": entry.key,
        "case_id": case["id"],
        "visibility": visibility,
        "expected_fields": expected,
        "expected_authors": authors,
        "rendered_text": text,
        "annotation_targets": targets,
        "rendering_issues": typeset_locator_issues(targets, actual_uris),
        "required_checks": required,
        "canonical_records": case["canonical_records"],
        "classification": occurrence_classification(text, family),
        "author_presentation": "initials" if family in INITIAL_FAMILIES else "full",
        "author_structure_visible": author_structure_visible(
            [_person(person, False) for person in entry.persons.get("author", ())]
        ),
    }


def annotate_project(cell, truth):
    from pypdf import PdfReader

    from .pages import page_anchors

    project = Path(cell["project"])
    reader = PdfReader(project / "main.pdf")
    actual_uris = [
        str(annotation.get_object()["/A"]["/URI"])
        for page in reader.pages
        for annotation in page.get("/Annots", [])
        if annotation.get_object().get("/A", {}).get("/URI")
    ]
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
            _case_expectation(
                cases[key], entries[key], recipe["venue"]["family"], body, actual_uris
            )
        )
    visible_keys = [
        key
        for (key, _), case in zip(bodies, annotations, strict=True)
        if case["classification"] != "omitted"
    ]
    anchors = page_anchors(
        project, visible_keys, {key: rendered_text(body)[0] for key, body in bodies}
    )
    for (key, _), case in zip(bodies, annotations, strict=True):
        if case["classification"] != "omitted":
            case["anchor"] = anchors[key]
    return {
        "venue": cell["venue"],
        "family": recipe["venue"]["family"],
        "pages": len(reader.pages),
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
            else:
                row["anchor"] = {key: case["anchor"][key] for key in ("page", "box")}
            if case["rendering_issues"]:
                row["issues"] = case["rendering_issues"]
            if case["expected_authors"] and case["expected_authors"][-1]["kind"] == "others":
                row["authors_shown"] = len(case["expected_authors"]) - 1
            if not case["author_structure_visible"]:
                row["author_grouping_erased"] = True
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
                "absent_fields": [
                    field
                    for field in ("title", "year")
                    if project["corpus"] == "rule-variants" and not entry.fields.get(field)
                ],
                "expected_authors": [
                    _person(person, project["family"] in INITIAL_FAMILIES)
                    for person in entry.persons.get("author", ())[: row.get("authors_shown")]
                ]
                + (
                    [{"given": "", "family": "others", "suffix": "", "kind": "others"}]
                    if "authors_shown" in row
                    else []
                ),
                "required_checks": visible_checks(case, project["family"], visibility),
                "expected_statuses": expected_statuses(case, project["family"], visibility),
                "required_issues": required_issues(case, visibility),
                "canonical_records": case["canonical_records"],
                "primary_sources": list(
                    dict.fromkeys(
                        truth["canonical_records"][key]["provider"]
                        for key in case["canonical_records"]
                        if truth["canonical_records"][key]["provider"] == "arxiv"
                        or truth["canonical_records"][key]["metadata"].get("publication_status")
                        in {"accepted", "published"}
                    )
                ),
                "classification": "omitted" if row.get("o") else "text",
                "anchor": row.get("anchor"),
                "author_structure_visible": not row.get("author_grouping_erased", False),
            }
        )
        if row.get("issues"):
            rendered = expanded["cases"][-1]
            for check in rendered["required_checks"]:
                if check["field"] in {issue["field"] for issue in row["issues"]}:
                    check["results"] = ["unknown"]
            rendered["expected_statuses"] = ["Needs review"]
            rendered["required_issues"].extend(
                {"field": issue["field"], "requirement": issue["code"]} for issue in row["issues"]
            )
    return expanded


def validate_gold_inventory(gold, ledger):
    from collections import Counter

    cells = (
        ledger["builds"]
        if ledger.get("matrix") == "stress"
        else ledger["renderable_builds"] + ledger["renderable_counterparts"]
    )

    def identities(rows):
        return Counter((row["venue"], row["corpus"], row["pdf_sha256"]) for row in rows)

    actual, required = identities(gold["projects"]), identities(cells)
    if not ledger.get("complete") or actual != required or any(n != 1 for n in actual.values()):
        raise ValueError(
            "Independent gold project inventory differs from the required build matrix"
        )
