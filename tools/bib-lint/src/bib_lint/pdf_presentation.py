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
    return _normalize_breaks(text, breaks)


def _normalize_breaks(text, breaks):
    pieces, positions, start, length = [], [], 0, 0
    for index in breaks:
        piece = _normalized(text[start:index])
        pieces.extend((piece, _normalized(text[index])))
        length += len(piece)
        positions.append(length)
        length += 1
        start = index + 1
    pieces.append(_normalized(text[start:]))
    return "".join(pieces), positions


def _wrapped(pdf, previous, following, part):
    fragment = pdf["fragments"][previous["fragment"]]["text"]
    return (
        following["fragment"] == previous["fragment"] + 1
        and previous["end"] == len(fragment)
        and following["start"] == 0
        and HYPHEN.search(fragment)
        and re.match(r"\w", part)
    )


def _positions(value, source, breaks):
    normalized = _normalized(value)
    start = source.find(normalized)
    if start < 0 or source.find(normalized, start + 1) >= 0:
        return normalized, []
    positions = [index - start for index in breaks if start < index < start + len(normalized) - 1]
    return normalized, positions


def _variants(value, source, breaks):
    normalized, positions = _positions(value, source, breaks)
    positions = positions[: MAX_VARIANTS.bit_length() - 1]
    variants = [value]
    for mask in range(1, 1 << len(positions)):
        removed = {index for bit, index in enumerate(positions) if mask & (1 << bit)}
        alternate = "".join(c for index, c in enumerate(normalized) if index not in removed)
        if alternate not in variants:
            variants.append(alternate)
    return tuple(variants)


def _matching_variant(value, source, breaks, canonical):
    """Match fixed word spans linearly; only proved hyphens may be absent or present."""
    normalized, positions = _positions(value, source, breaks)
    if not positions:
        return None
    target, cursor, previous, removed = normalize(canonical), 0, 0, set()
    for index in positions:
        fixed = normalize(normalized[previous:index])
        if not target.startswith(fixed, cursor):
            return None
        cursor += len(fixed)
        if target[cursor : cursor + 1] == " ":
            cursor += 1
        else:
            removed.add(index)
        previous = index + 1
    if target[cursor:] != normalize(normalized[previous:]):
        return None
    candidate = "".join(c for index, c in enumerate(normalized) if index not in removed)
    return candidate if normalize(candidate) == target else None


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
            equivalent = _matching_variant(value, name, name_breaks, found[index].get(part))
            if equivalent is not None:
                authors[index][part] = equivalent
    return authors


def _author_comparison(item, original, found):
    alternate = _author_presentation(item, original, found)
    source, _ = _field_source(item, "authors")
    if _ambiguous_adjacent_groups(alternate, found, source):
        return "unknown"
    if alternate == original:
        return None
    return next(
        c["result"]
        for c in compare_fields({"authors": alternate}, {"authors": found})
        if c["field"] == "authors"
    )


def _ambiguous_adjacent_groups(original, found, source):
    if len(original) != len(found) + 1:
        return False
    source = " ".join(source.split())
    for index, canonical in enumerate(found):
        first, last = original[index : index + 2]
        if (
            first.get("kind") == "literal"
            or last.get("given")
            or last.get("suffix")
            or first.get("suffix")
            or last.get("kind") == "literal"
        ):
            continue
        given = " ".join(first.get(part, "") for part in ("given", "family"))
        if normalize(given) != normalize(canonical.get("given")) or normalize(
            last.get("family")
        ) != normalize(canonical.get("family")):
            continue
        pair = rf"(?<!\w){re.escape(given)}\s*,\s*{re.escape(last['family'])}(?!\w)"
        occurrences = re.findall(rf"(?<!\w){re.escape(given)}(?!\w)", source, re.IGNORECASE)
        if len(occurrences) != 1 or not re.search(pair, source, re.IGNORECASE):
            continue
        alternate = (
            original[:index] + [{"given": given, "family": last["family"]}] + original[index + 2 :]
        )
        comparison = next(
            c
            for c in compare_fields({"authors": alternate}, {"authors": found})
            if c["field"] == "authors"
        )
        if comparison["result"] in {"match", "unknown"}:
            return True
    return False


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
            if state in {"match", "partial_match", "unknown"} and state != comparison["result"]:
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
        source, breaks = _field_source(item, field)
        candidate = _matching_variant(original[field], source, breaks, found[field])
        if candidate is not None and normalize(candidate) != normalize(original[field]):
            return "match"
    return None
