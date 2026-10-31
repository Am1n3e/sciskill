"""Bounded alternate readings of hyphens proved by original PDF line fragments."""

import copy
import re
import unicodedata

from bib_lint.verification.matching import compare_fields, input_record, normalize

HYPHEN = re.compile(r"\w[-\u2010\u00ad]$")
MAX_VARIANTS = 16


def _normalized(value):
    return unicodedata.normalize("NFKC", value)


def _field_source(item, field):
    pdf = item["pdf"]
    evidence = pdf["field_evidence"]
    aliases = ("venue", "journal", "booktitle") if field == "venue" else (field,)
    mappings = next((evidence[key] for key in aliases if key in evidence), [])
    text, breaks, previous = "", [], None
    for mapping in mappings:
        if "fragment" not in mapping:
            continue
        fragment = pdf["fragments"][mapping["fragment"]]["text"]
        part = fragment[mapping["start"] : mapping["end"]]
        contiguous = (
            previous
            and mapping["fragment"] == previous["fragment"]
            and (mapping["start"] == previous["end"])
        )
        wrapped = previous and _wrapped(pdf, previous, mapping, part)
        if wrapped:
            breaks.append(len(text) - 1)
        separator = "" if not text or contiguous or wrapped else " "
        text += separator + part
        previous = mapping
    return _normalized(text), [len(_normalized(text[:index])) for index in breaks]


def _wrapped(pdf, previous, following, part):
    fragment = pdf["fragments"][previous["fragment"]]["text"]
    return (
        following["fragment"] == previous["fragment"] + 1
        and previous["end"] == len(fragment)
        and following["start"] == 0
        and HYPHEN.search(fragment)
        and re.match(r"\w", part)
    )


def _variants(value, source, breaks):
    normalized = _normalized(value)
    start = source.find(normalized)
    if start < 0 or source.find(normalized, start + 1) >= 0:
        return (value,)
    positions = [index - start for index in breaks if start <= index < start + len(normalized)]
    positions = positions[
        : MAX_VARIANTS.bit_length() - 1
    ]  # At most 16 interpretations per field/name part.
    variants = [value]
    for mask in range(1, 1 << len(positions)):
        removed = {index for bit, index in enumerate(positions) if mask & (1 << bit)}
        alternate = "".join(
            character for index, character in enumerate(normalized) if index not in removed
        )
        if alternate not in variants:
            variants.append(alternate)
    return tuple(variants)


def text_variants(item, field, value):
    source, breaks = _field_source(item, field)
    return _variants(value, source, breaks)


def _author_presentation(item, original, found):
    source, breaks = _field_source(item, "authors")
    people = item["entry"]["persons"].get("author", [])
    authors = copy.deepcopy(original)
    cursor = 0
    for index, person in enumerate(people):
        if index >= len(found) or not person.get("bibtex"):
            continue
        name = _normalized(person["bibtex"])
        start = source.find(name, cursor)
        if start < 0:
            continue
        cursor = start + len(name)
        name_breaks = [position - start for position in breaks if start <= position < cursor]
        for part in ("given", "family", "suffix"):
            value = authors[index].get(part, "")
            variants = _variants(value, name, name_breaks)
            equivalent = next(
                (v for v in variants if normalize(v) == normalize(found[index].get(part))), None
            )
            if equivalent is not None:
                authors[index][part] = equivalent
    return authors


def _author_comparison(item, original, found):
    alternate = _author_presentation(item, original, found)
    if alternate == original:
        return None
    return next(
        c["result"]
        for c in compare_fields({"authors": alternate}, {"authors": found})
        if c["field"] == "authors"
    )


def apply_presentation(methods, item):
    """Change comparison states, preserving the actual input and canonical records."""
    copied, changed = copy.deepcopy(methods), False
    original = input_record(item["entry"])
    for method in copied:
        if method.get("status") != "found" or not method.get("authority"):
            continue
        found = method["found_ref"]
        matched = set()
        for comparison in method.get("comparisons", []):
            if comparison["result"] == "match":
                continue
            field = comparison["field"]
            state = _comparison(item, field, original, found)
            if state in {"match", "partial_match"} and state != comparison["result"]:
                comparison["result"] = state
                changed = True
                matched.add(field)
        method["differences"] = [
            d for d in method.get("differences", []) if d["field"] not in matched
        ]
    return copied, changed


def _comparison(item, field, original, found):
    if field == "authors":
        return _author_comparison(item, original.get("authors", []), found.get("authors", []))
    if field in {"title", "venue"} and original.get(field) and found.get(field):
        if any(
            normalize(variant) == normalize(found[field])
            for variant in text_variants(item, field, original[field])[1:]
        ):
            return "match"
    return None
