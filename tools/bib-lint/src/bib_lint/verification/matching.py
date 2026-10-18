"""Conservative identity selection and explicit field comparisons."""

import codecs
import html
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import unquote

import latexcodec  # noqa: F401 -- registers the latex codec
from pybtex.database import Person


def plain(value):
    return codecs.decode(html.unescape(str(value or "")), "ulatex")


def normalize(value):
    text = unicodedata.normalize("NFKC", plain(value).replace("{", "").replace("}", "")).casefold()
    return " ".join(re.findall(r"\w+", text))


def doi(value):
    return (
        re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(str(value or "")), flags=re.I
        )
        .strip()
        .lower()
    )


def arxiv_id(value):
    value = str(value or "").strip()
    match = re.search(
        r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)?"
        r"((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)",
        value,
        re.I,
    )
    return match.group(1) if match else None


def name_parts(value):
    if isinstance(value, dict):
        return value
    person = Person(value)
    return {
        "given": " ".join(person.first_names + person.middle_names),
        "family": " ".join(person.prelast_names + person.last_names),
        "suffix": " ".join(person.lineage_names),
    }


def input_record(entry):
    fields = entry.get("fields", {})
    authors = []
    for person in entry.get("persons", {}).get("author", []):
        authors.append(
            {
                "given": " ".join(person.get("first", []) + person.get("middle", [])),
                "family": " ".join(person.get("prelast", []) + person.get("last", [])),
                "suffix": " ".join(person.get("lineage", [])),
            }
        )
    identifiers = {}
    if fields.get("doi"):
        identifiers["doi"] = doi(fields["doi"])
    url = fields.get("url", "")
    if not identifiers.get("doi") and re.match(r"https?://(?:dx\.)?doi\.org/", url):
        identifiers["doi"] = doi(url)
    arxiv = arxiv_id(fields.get("eprint"))
    if not arxiv and "arxiv.org/" in url.lower():
        arxiv = arxiv_id(url)
    if not arxiv and "arxiv" in fields.get("journal", "").lower():
        arxiv = arxiv_id(fields["journal"])
    if arxiv:
        identifiers["arxiv"] = arxiv
    venue = fields.get("journal") or fields.get("booktitle")
    preprint = "arxiv" in normalize(venue) or (bool(arxiv) and not venue)
    return {
        "record_type": "preprint" if preprint else "publication",
        "title": fields.get("title"),
        "authors": authors,
        "year": fields.get("year"),
        "venue": fields.get("journal") or fields.get("booktitle"),
        "identifiers": identifiers,
    }


def author_names(record):
    return [
        normalize(" ".join(str(author.get(k) or "") for k in ("given", "family", "suffix")))
        for author in record.get("authors", [])
    ]


def families(record):
    return {normalize(a.get("family")) for a in record.get("authors", []) if a.get("family")}


def title_similarity(a, b):
    return SequenceMatcher(None, normalize(a.get("title")), normalize(b.get("title"))).ratio()


def identity_match(a, b):
    """A resolved identifier alone cannot validate a record with an unrelated title."""
    if not a.get("title") or not b.get("title"):
        return False
    shared = any(
        v and b.get("identifiers", {}).get(k) == v for k, v in a.get("identifiers", {}).items()
    )
    overlap = bool(families(a) & families(b))
    return (shared and title_similarity(a, b) >= 0.88) or (
        title_similarity(a, b) >= 0.96 and overlap
    )


def same_record(a, b):
    """Do not merge different DOIs or unlinked preprint/publication versions."""
    ai, bi = a.get("identifiers", {}), b.get("identifiers", {})
    if ai.get("doi") and bi.get("doi") and ai["doi"] != bi["doi"]:
        return False
    if ai.get("arxiv") and bi.get("arxiv") and ai["arxiv"] != bi["arxiv"]:
        return False
    shared = any(v and bi.get(k) == v for k, v in ai.items())
    if shared:
        return identity_match(a, b)
    return (
        normalize(a.get("title")) == normalize(b.get("title"))
        and bool(author_names(a))
        and author_names(a) == author_names(b)
        and str(a.get("year")) == str(b.get("year"))
        and bool(a.get("venue"))
        and normalize(a["venue"]) == normalize(b.get("venue"))
    )


def compare_fields(original, found):
    comparisons = []
    for field in ("title", "authors", "year", "venue"):
        left, right = original.get(field), found.get(field)
        state = "unknown"
        if left and right:
            if field == "authors":
                state = _compare_authors(original, found, left, right)
                # Compatible initials or missing given names still require review.
            else:
                same = normalize(left) == normalize(right)
                if field == "venue" and "arxiv" in normalize(left) and "arxiv" in normalize(right):
                    same = True
                state = "match" if same else "mismatch"
                if field == "venue" and state == "mismatch":
                    state = "unknown"  # Venue abbreviations need review, not an invented fix.
        elif field == "venue" and not left:
            state = "not_checked"
        comparisons.append({"field": field, "input": left, "found": right, "result": state})
    for key, value in original.get("identifiers", {}).items():
        other = found.get("identifiers", {}).get(key)
        compatible_arxiv = (
            key == "arxiv"
            and other
            and not re.search(r"v\d+$", value)
            and value == re.sub(r"v\d+$", "", other)
        )
        comparisons.append(
            {
                "field": key,
                "input": value,
                "found": other,
                "result": "unknown"
                if not other
                else "match"
                if other == value or compatible_arxiv
                else "mismatch",
            }
        )
    return comparisons


def select_result(name, original, candidates, *, authority=False, lookup="search"):
    matches = []
    matched_candidates = []
    rejected_candidates = []
    for record in candidates:
        if identity_match(original, record):
            matched_candidates.append(record)
            if not any(same_record(record, r) for r in matches):
                matches.append(record)
        else:
            rejected_candidates.append(record)
    result = {
        "name": name,
        "status": "not_found",
        "lookup": lookup,
        "authority": authority,
        "found_ref": None,
        "agrees_with_consensus": None,
        "differences": [],
    }
    if len(matches) > 1:
        result.update(status="ambiguous", candidates=matches)
    elif matches:
        record = matches[0]
        comparisons = compare_fields(original, record)
        result.update(
            status="found",
            found_ref=record,
            source_url=record.get("url"),
            comparisons=comparisons,
            version_uncertain=(
                original.get("record_type", "publication")
                != record.get("record_type", "publication")
            ),
            differences=[c for c in comparisons if c["result"] == "mismatch"],
        )
    if matched_candidates:
        result["matched_candidates"] = matched_candidates
    if rejected_candidates:
        result["rejected_candidates"] = rejected_candidates
    return result


def _compare_authors(original, found, left, right):
    state = "unknown"
    a, b = author_names(original), author_names(found)
    if a and a[-1] == "others" and "others" not in a[:-1]:
        state = _compare_author_prefix(a, b, left, right)
    elif a == b:
        state = "match"
    elif len(a) != len(b) and "others" not in a:
        state = "mismatch"
    elif [normalize(p.get("family")) for p in left] != [normalize(p.get("family")) for p in right]:
        state = "mismatch" if "others" not in a else "unknown"
    else:
        for x, y in zip(left, right, strict=True):
            gx, gy = (
                normalize(x.get("given")).split(),
                normalize(y.get("given")).split(),
            )
            if gx and gy and gx[0][0] != gy[0][0]:
                state = "mismatch"
    return state


def _compare_author_prefix(a, b, left, right):
    state = "unknown"
    prefix = a[:-1]
    if prefix and len(b) > len(prefix) and prefix == b[: len(prefix)]:
        state = "partial_match"
    elif len(b) < len(prefix):
        state = "mismatch"
    elif prefix:
        prefix_check = compare_fields({"authors": left[:-1]}, {"authors": right[: len(prefix)]})[1][
            "result"
        ]
        state = "mismatch" if prefix_check == "mismatch" else "unknown"
    return state
