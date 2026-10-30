"""Conservative identity selection and explicit field comparisons."""

import codecs
import html
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import unquote

import latexcodec  # noqa: F401 -- registers the latex codec
from pybtex.database import Person

_FONT_ARGUMENT = re.compile(
    r"(?<!\\)\\(?:emph|textbf|textit|textrm|textsf|texttt|textsc|textnormal|textup|textsl|textmd)"
    r"(?=\s*\{)"
)
_FONT_DECLARATION = re.compile(
    r"(?<!\\)\\(?:bfseries|mdseries|itshape|upshape|slshape|scshape|rmfamily|sffamily|ttfamily|normalfont)"
    r"(?![A-Za-z])"
)
_ARXIV_VENUE = re.compile(
    r"arxiv(?:[\s-]+(?:preprint|e[\s-]*prints?))?"
    r"(?:[\s,:]+(?:arxiv\s*:\s*)?"
    r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)?",
    re.I,
)


def plain(value):
    # Only erase known presentation commands; this never evaluates TeX or macros.
    text = html.unescape(str(value or ""))
    text = _FONT_ARGUMENT.sub("", _FONT_DECLARATION.sub("", text))
    return codecs.decode(text, "ulatex")


def normalize(value):
    text = unicodedata.normalize("NFKC", plain(value).replace("{", "").replace("}", "")).casefold()
    return " ".join(re.findall(r"\w+", text))


def doi(value):
    # Do not pass a URI through the TeX codec: a raw % starts a TeX comment.
    # Decode presentation escapes first so \%2F does not become a spurious \/.
    text = re.sub(r"\\([%_&#])", r"\1", html.unescape(str(value or ""))).strip()
    if re.match(r"https?://(?:dx\.)?doi\.org/", text, flags=re.I):
        # URI query/fragment delimiters are not part of the DOI. Decode the path
        # afterwards: encoded ? and # can legitimately belong to the identifier.
        # Split explicitly so a URI parser cannot silently erase invalid controls.
        text = re.split(r"[?#]", text, maxsplit=1)[0]
    return (
        re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(text).strip(), flags=re.I)
        .strip()
        .lower()
    )


def is_arxiv_venue(value):
    """Recognize archive aliases, including a complete legacy journal locator."""
    text = plain(value).replace("{", "").replace("}", "").strip()
    return bool(_ARXIV_VENUE.fullmatch(text))


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
    from bib_lint.verification.input_checks import strict_arxiv

    fields = entry.get("fields", {})
    authors = []
    for person in entry.get("persons", {}).get("author", []):
        author = {
            "given": " ".join(person.get("first", []) + person.get("middle", [])),
            "family": " ".join(person.get("prelast", []) + person.get("last", [])),
            "suffix": " ".join(person.get("lineage", [])),
        }
        if person.get("kind") in {"literal", "others"}:
            author["kind"] = person["kind"]
        authors.append(author)
    identifiers = {}
    if fields.get("doi"):
        identifiers["doi"] = doi(fields["doi"])
    url = fields.get("url", "").strip()
    if not identifiers.get("doi") and re.match(r"https?://(?:dx\.)?doi\.org/", url, flags=re.I):
        identifiers["doi"] = doi(url)
    arxiv = strict_arxiv(fields.get("eprint", "")) or arxiv_id(fields.get("eprint"))
    if not arxiv:
        arxiv = strict_arxiv(url)
    if not arxiv and "arxiv" in fields.get("journal", "").lower():
        arxiv = arxiv_id(fields["journal"])
    if arxiv:
        identifiers["arxiv"] = arxiv
    venue = fields.get("journal") or fields.get("booktitle")
    preprint = is_arxiv_venue(venue) or (bool(arxiv) and not venue)
    return {
        "record_type": "preprint" if preprint else "publication",
        "title": fields.get("title"),
        "authors": authors,
        "year": fields.get("year"),
        "venue": fields.get("journal") or fields.get("booktitle"),
        "identifiers": identifiers,
        "input_fields": fields.copy(),
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
        and _compare_author_lists(a["authors"], b["authors"]) == "match"
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
                state = _compare_authors(left, right)
                # Compatible initials or missing given names still require review.
            else:
                same = normalize(left) == normalize(right)
                if field == "venue" and is_arxiv_venue(left) and is_arxiv_venue(right):
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
    from bib_lint.verification.input_checks import apply_input_checks

    return apply_input_checks(comparisons, original, found)


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


def _compare_authors(left, right):
    if any(_is_others(a) for a in right) or any(_is_others(a) for a in left[:-1]):
        return "unknown"
    if _is_others(left[-1]):
        return _compare_author_prefix(left[:-1], right)
    return _compare_author_lists(left, right)


def _is_others(author):
    return (
        author.get("kind") != "literal"
        and not author.get("given")
        and not author.get("suffix")
        and normalize(author.get("family")) == "others"
    )


def _author_kind(author):
    return author.get("kind") or ("person" if author.get("given") else "")


def _compare_author(left, right):
    kinds = {_author_kind(left), _author_kind(right)} - {""}
    if len(kinds) > 1:
        return "unknown"
    a, b = (
        tuple(normalize(p.get(k)) for k in ("given", "family", "suffix")) for p in (left, right)
    )
    if not a[1] or not b[1]:
        return "unknown"
    if a[1] != b[1]:
        return "mismatch"
    if a == b:
        return "match"
    if a[0] and b[0] and a[0][0] != b[0][0]:
        return "mismatch"
    return "unknown"  # Compatible initials or absent suffixes need review.


def _compare_author_lists(left, right):
    if len(left) != len(right):
        return "mismatch"
    states = [_compare_author(a, b) for a, b in zip(left, right, strict=True)]
    if "mismatch" in states:
        return "mismatch"
    return "match" if all(s == "match" for s in states) else "unknown"


def _compare_author_prefix(prefix, right):
    if not prefix:
        return "unknown"
    if len(right) < len(prefix):
        return "mismatch"
    result = _compare_author_lists(prefix, right[: len(prefix)])
    if result == "match" and len(right) > len(prefix):
        return "partial_match"
    return "mismatch" if result == "mismatch" else "unknown"
