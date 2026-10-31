"""Bounded local citation grammar with typography and explicit uncertainty."""

import re
import unicodedata
from collections import defaultdict

from pybtex.database import Person
from pybtex.exceptions import PybtexError

from bib_lint.pdf_input.layout import LABEL
from bib_lint.verification.input_checks import ALIASES, compatible, locator, url_locators

YEAR = re.compile(r"(?<!\d)((?:18|19|20)\d{2})[a-z]?(?!\d)")
URL = re.compile(r"https?://[^\s<>]+", re.I)
DOI = re.compile(r"(?:doi:\s*)?(10\.\d{4,9}/[^\s<>]+)", re.I)
INITIAL = re.compile(r"(?:\b[A-Z]|\bJr|\bSr|\bDr|\bProf|\bet)\.$")


DIACRITICS = {
    "´": "\u0301",
    "¨": "\u0308",
    "ˆ": "\u0302",
    "ˇ": "\u030c",
    "˘": "\u0306",
    "˜": "\u0303",
    "˙": "\u0307",
    "˚": "\u030a",
    "¸": "\u0327",
    "˝": "\u030b",
    "˛": "\u0328",
    "ˋ": "\u0300",
}


def _semantic_text(value):
    accent = "[" + "".join(DIACRITICS) + "]"
    value = re.sub(r"([^\W\d_])(" + accent + ")", lambda m: m[1] + DIACRITICS[m[2]], value)
    return unicodedata.normalize("NFKC", value)


def diagnostic(code, message, fields, **extra):
    return {"code": code, "message": message, "fields": fields, **extra}


def _join(lines):
    text, styles, positions = "", [], []
    for index, line in enumerate(lines):
        part = line["text"]
        separator = " " if text else ""
        # URLs/identifiers are not prose: a typeset line break is not an identifier character.
        if text and (
            _wrapped_locator(text, part) or (text.endswith("-") and re.match(r"\w", part))
        ):
            separator = ""
        offset = len(text) + len(separator)
        text += separator + part
        positions.extend([None] * len(separator))
        positions.extend((index, character) for character in range(len(part)))
        styles.extend(
            {**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in line["_spans"]
        )
    return text, styles, positions


def _wrapped_locator(text, continuation):
    if not re.search(r"https?://\S*$|\b10\.\d{4,9}/\S*$", text):
        return text.endswith("/")
    if re.match(r"(?:Accessed|Retrieved|Visited|Available|URL|doi)\b", continuation, re.I):
        return False
    return not text.endswith(".") or bool(re.match(r"[a-z]{2,}(?:/|\.|$)", continuation))


def _sentences(text):
    boundaries = []
    for match in re.finditer(r"[.!?]\s+|[.!?]$", text):
        prefix = text[: match.start() + 1]
        if INITIAL.search(prefix) or re.search(r"\b(?:pp|vol|eds?)\.$", prefix, re.I):
            continue
        boundaries.append((match.start(), match.end()))
    return boundaries


def _corporate(value):
    return bool(
        re.search(
            r"\b(?:Group|Team|Consortium|Committee|Collaboration|Organization|Organisation|ISO|IEC)\b",
            value,
            re.I,
        )
    )


def _name_like(value):
    if _corporate(value):
        return True
    words = value.split()
    stop = {
        "the",
        "a",
        "an",
        "of",
        "for",
        "learning",
        "language",
        "models",
        "measuring",
        "towards",
        "using",
        "beyond",
        "with",
        "without",
        "evaluation",
        "benchmark",
        "in",
    }
    tokens = {
        w.lower().strip(",.") for w in words if not re.fullmatch(r"(?:[A-Z]\.)+", w.rstrip(","))
    }
    return bool(words) and not (tokens & stop) and ":" not in value


def _literal_name(value, kind):
    return {
        "first": [],
        "middle": [],
        "prelast": [],
        "last": [_semantic_text(value)],
        "lineage": [],
        "kind": kind,
        "bibtex": value,
    }


def _person_name(value):
    if value.count(",") > 2:
        raise ValueError("Name punctuation is ambiguous")
    original = value
    value = _semantic_text(value)
    value = re.sub(r"\s*\([^)]*[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af][^)]*\)", "", value)
    suffix = re.search(r",?\s+(Jr\.?|Sr\.?|II|III|IV)$", value)
    lineage = []
    if suffix:
        value = value[: suffix.start()].rstrip(" ,")
        token = suffix[1]
        lineage = [token.rstrip(".") + "." if token[:2] in {"Jr", "Sr"} else token]
    person = Person(value)
    return {
        "first": person.first_names,
        "middle": person.middle_names,
        "prelast": person.prelast_names,
        "last": person.last_names,
        "lineage": lineage or person.lineage_names,
        "kind": "person",
        "bibtex": original,
    }


def _inverted_initials(value):
    match = re.match(r"^([^,]+),\s*[A-Z]\.", value)
    if not match:
        return False
    words = match[1].split()
    return len(words) == 1 or any(word[:1].islower() for word in words)


def _author_strings(value):
    if _inverted_initials(value):
        value = re.sub(r",\s*(?:and\s+)?(?=[A-Z][\w'’ -]+,\s*[A-Z]\.)", " and ", value)
        return re.split(r"\s+and\s+|;\s*", value)
    names = []
    for group in re.split(r",?\s+and\s+|;\s*", value):
        parts = group.strip(" ,").split(",")
        inverted = len(parts) == 2 and (
            len(parts[0].split()) == 1 or parts[0].strip().split()[0].islower()
        )
        if inverted or re.search(r",\s*(?:Jr|Sr)\.?$", group):
            names.append(group)
        else:
            names.extend(parts)
    return names


def _authors(value):
    value = re.sub(r"\bet\s+al\.?", "others", value).strip(" ,:;")
    value = re.sub(r"(?<!and)\s+others\b", " and others", value)
    if not value:
        return []
    if _corporate(value):
        return [_literal_name(value.rstrip("."), "literal")]
    names = []
    for name in _author_strings(value):
        name = name.strip(" ,")
        if name:
            names.append(
                _literal_name("others", "others")
                if name.lower().rstrip(".") == "others"
                else _person_name(name)
            )
    return names


def _parsed_authors(authors, diagnostics):
    if not authors:
        return {}
    try:
        return {"author": _authors(authors)}
    except (PybtexError, ValueError):
        diagnostics.append(
            diagnostic("ambiguous_authors", "Printed author punctuation needs review", ["authors"])
        )
        return {}


def _title_tail(rest):
    rest = rest.lstrip()
    if re.match(
        r"^(?:(?:URL|doi)\s*:?\s*)?(?:https?://|10\.\d{4,9}/)|^arxiv\s*:|^Journal\s+of\b",
        rest,
        re.I,
    ):
        return "", rest
    pairs = {'"': '"', "“": "”", "‘": "’"}
    if rest[:1] in pairs:
        closing = rest.find(pairs[rest[0]], 1)
        if closing > 0:
            return rest[1:closing].strip(" ."), rest[closing + 1 :].lstrip(" .")
    boundary = _sentences(rest)
    if not boundary:
        return rest.strip(" ."), ""
    end, tail_start = boundary[0]
    return rest[:end].strip(), rest[tail_start:]


def _inverted_boundary(text):
    if not _inverted_initials(text):
        return None
    for boundary in re.finditer(r"\.\s+", text):
        prefix = text[: boundary.start() + 1]
        following = text[boundary.end() :].split(maxsplit=1)
        if not following:
            continue
        next_word = following[0]
        continuing = next_word.lower().strip(" ,.") in {"and", "others", "et", "al"}
        if INITIAL.search(prefix) and not continuing and not re.fullmatch(r"[A-Z]\.", next_word):
            return prefix, boundary.end()
    return None


def _author_boundary(text):
    for colon in re.finditer(r":\s+", text):
        prefix = text[: colon.start()].strip()
        if prefix.endswith(".") and "," in prefix and _name_like(prefix):
            return prefix, colon.end()
    inverted = _inverted_boundary(text)
    if inverted:
        return inverted
    boundaries = _sentences(text)
    if not boundaries:
        return "", 0
    first_end, next_start = boundaries[0]
    first = text[:first_end].strip()
    year = re.search(r"\b((?:18|19|20)\d{2})[a-z]?\)?\s*$", first)
    authors = first[: year.start()].strip(" (,.") if year else first
    return (authors, next_start) if _name_like(authors) else ("", 0)


def _segments(text):
    authors, next_start = _author_boundary(text)
    rest = text[next_start:]
    rest = re.sub(r"^\s*\(?(?:18|19|20)\d{2}[a-z]?\)?[.,]?\s+", "", rest)
    title, tail = _title_tail(rest)
    title_start = text.find(title or rest, next_start) if title or rest else len(text)
    return authors, title, tail, max(0, title_start)


def _trim_locator(value):
    value = value.rstrip(".,;")
    for opening, closing in (("(", ")"), ("[", "]")):
        while value.endswith(closing) and value.count(closing) > value.count(opening):
            value = value[:-1]
    return value


def _locator_choices(text, uris):
    values = defaultdict(list)
    supplied = [(m[0], None, m.span()) for m in URL.finditer(text)]
    supplied.extend((u["uri"], i, None) for i, u in enumerate(uris))
    for raw, uri_index, span in supplied:
        raw = _trim_locator(raw)
        values["url"].append((raw, uri_index, span))
        for provider, value in url_locators(raw):
            values[provider].append((value, uri_index, span))
    for match in DOI.finditer(text):
        value = _trim_locator(match[1])
        values["doi"].append((value, None, (match.start(1), match.start(1) + len(value))))
    stripped = URL.sub(lambda m: " " * len(m[0]), text)
    stripped = DOI.sub(lambda m: " " * len(m[0]), stripped)
    for match in re.finditer(r"(?:arxiv\s*:\s*)?(\d{4}\.\d{4,5}[^\s,;]*)", stripped, re.I):
        value = _trim_locator(match[1])
        values["arxiv"].append((value, None, (match.start(1), match.start(1) + len(value))))
    return values


def _locators(text, uris):
    fields, evidence, diagnostics = {}, {}, []
    for provider, choices in _locator_choices(text, uris).items():
        by_value = {}
        for choice in choices:
            by_value.setdefault(choice[0], choice)
        unique = list(by_value.values())
        aliases = ("url",) if provider == "url" else ALIASES.get(provider, (provider,))
        for alias, (value, uri_index, span) in zip(aliases, unique, strict=False):
            fields[alias] = value
            evidence[alias] = {"uri": uri_index} if uri_index is not None else {"span": span}
        canonical = (
            [locator(provider, value) for value, _, _ in unique] if provider != "url" else []
        )
        valid = [value for value in canonical if value]
        if any(not compatible(provider, a, b) for a in valid for b in valid):
            diagnostics.append(
                diagnostic(
                    "locator_conflict",
                    f"Printed text and URI evidence supply conflicting {provider} locators",
                    [provider],
                    result="mismatch",
                )
            )
    if "arxiv" in fields:
        fields["eprint"] = fields["arxiv"]
        evidence["eprint"] = evidence["arxiv"]
    return fields, evidence, diagnostics


def _venue(tail, styles, text, title_end):
    italic = [
        s
        for s in styles
        if s["start"] >= title_end
        and re.search(r"italic|oblique|cmti|ptmri|Times-Italic", s["font"], re.I)
    ]
    if italic:
        start, end = italic[0]["start"], italic[0]["end"]
        for span in italic[1:]:
            if span["start"] - end > 3:
                break
            end = span["end"]
        return text[start:end].strip(" ,.")
    tail = re.split(r"\b(?:doi\s*:|https?://|URL\b|ISBN\b|BibTeX\b)", tail, maxsplit=1, flags=re.I)[
        0
    ]
    tail = re.sub(r"\s*\((?:18|19|20)\d{2}[a-z]?\)\.?$", "", tail.strip())
    tail = re.sub(r"^In\s*:?[ \t]+", "", tail)
    return re.split(r",\s*(?:pp?\.?|pages|\d)|\.\s|[.;]$", tail, maxsplit=1)[0].strip(" ,.;()")


def _publication_year(content, title, title_start, tail):
    prefix = content[:title_start]
    prefix_year = YEAR.search(prefix)
    if prefix_year:
        return prefix_year[1], prefix_year.span(1)
    searchable = tail or content
    searchable = re.split(
        r"\b(?:accessed|retrieved|visited|BibTeX|ISBN)\b", searchable, maxsplit=1, flags=re.I
    )[0]
    searchable = URL.sub(lambda m: " " * len(m[0]), searchable)
    searchable = DOI.sub(lambda m: " " * len(m[0]), searchable)
    searchable = re.sub(r"\b\d{4}\.\d{4,5}\S*", lambda m: " " * len(m[0]), searchable)
    matches = [
        match
        for match in YEAR.finditer(searchable)
        if re.match(r"\s*(?:[).,;]|$)", searchable[match.end() :])
    ]
    if not matches:
        return None, None
    chosen = matches[-1]
    # A title's date is part of the title, not independent publication evidence.
    offset = content.find(tail) if tail else 0
    absolute = offset + chosen.start(1)
    if title_start <= absolute < title_start + len(title):
        return None, None
    return chosen[1], (absolute, absolute + len(chosen[1]))


def _publication_date(content, title, title_start, tail):
    year, span = _publication_year(content, title, title_start, tail)
    suffix = re.search(r",\s*((?:18|19|20)\d{2})[a-z]?$", title)
    if year is None and suffix:
        year = suffix[1]
        span = (title_start + suffix.start(1), title_start + suffix.end(1))
        title = title[: suffix.start()].rstrip()
    return title, year, span


def _span_mappings(positions, start, end):
    mappings = []
    for position in positions[start:end]:
        if position is None:
            continue
        fragment, character = position
        if mappings and mappings[-1]["fragment"] == fragment and mappings[-1]["end"] == character:
            mappings[-1]["end"] += 1
        else:
            mappings.append({"fragment": fragment, "start": character, "end": character + 1})
    return mappings


def _field_mappings(fields, locator_evidence, positions, text, base, title_start, year_span):
    evidence = {}
    for field, value in fields.items():
        if field in locator_evidence:
            source = locator_evidence[field]
            if "uri" in source:
                evidence[field] = [source]
                continue
            start, end = source["span"]
            start, end = base + start, base + end
        elif field == "year":
            start, end = base + year_span[0], base + year_span[1]
        else:
            search_start = base + title_start if field == "title" else base
            start = text.find(value, search_start)
            end = start + len(value)
        if start >= 0:
            evidence[field] = _span_mappings(positions, start, end)
    return evidence


def _clipped_findings(lines, evidence):
    findings = []
    locator_fields = {"url", "doi", "eprint", *ALIASES, *(a for v in ALIASES.values() for a in v)}
    for index, line in enumerate(lines):
        if not line.get("_clipped"):
            continue
        fields = {
            field
            for field, mappings in evidence.items()
            if any(mapping.get("fragment") == index for mapping in mappings)
        }
        if URL.search(line["text"]) or DOI.search(line["text"]):
            fields &= locator_fields
        findings.append(
            diagnostic(
                "clipped_text",
                "Some decoded reference text extends outside the visible PDF page",
                sorted(fields),
                page=line["page"],
            )
        )
    return findings


def _diacritic_findings(lines, evidence):
    findings = []
    ambiguous = re.compile(r"(?:^|\s)([" + "".join(DIACRITICS) + r"])(?=\w)")
    for index, line in enumerate(lines):
        offsets = [m.start(1) for m in ambiguous.finditer(line["text"])]
        fields = {
            field
            for field, mappings in evidence.items()
            if any(
                mapping.get("fragment") == index
                and any(mapping["start"] <= offset < mapping["end"] for offset in offsets)
                for mapping in mappings
            )
        }
        if fields:
            findings.append(
                diagnostic(
                    "ambiguous_diacritic",
                    "A separated PDF accent needs text interpretation review",
                    sorted(fields),
                    page=line["page"],
                )
            )
    return findings


def _entry_type(tail, venue):
    if re.match(r"In\s*:?\s", tail) and re.search(
        r"\b(?:conference|proceedings|workshop|symposium)\b", tail, re.I
    ):
        return "inproceedings"
    return "article" if re.search(r"\b(?:journal|transactions|letters)\b", venue, re.I) else "misc"


def parse_reference(lines, key, uris):
    text, styles, positions = _join(lines)
    label = LABEL.match(text)
    label_value = next((g for g in label.groups() if g), None) if label else None
    content = text[label.end() :] if label else text
    authors, title, tail, title_start = _segments(content)
    fields, locator_evidence, diagnostics = _locators(content, uris)
    title, year, year_span = _publication_date(content, title, title_start, tail)
    if year:
        fields["year"] = year
    if title:
        fields["title"] = title.strip(" .,")
    venue = _venue(tail, styles, text, (label.end() if label else 0) + title_start + len(title))
    if venue:
        fields["journal"] = venue
    persons = _parsed_authors(authors, diagnostics)
    for field in ("title", "authors", "year"):
        if not (persons.get("author") if field == "authors" else fields.get(field)):
            diagnostics.append(
                diagnostic(
                    "missing_" + field, f"No reliable printed {field} could be recovered", [field]
                )
            )
    if re.search(r"\(cid:\d+\)|\ufffd", content):
        diagnostics.append(
            diagnostic("unreadable_text", "Some PDF glyphs have no usable text mapping", [])
        )
    fragments = [
        {k: line[k] for k in ("page", "x0", "top", "x1", "bottom", "text")} for line in lines
    ]
    base = label.end() if label else 0
    evidence = _field_mappings(
        fields, locator_evidence, positions, text, base, title_start, year_span
    )
    if persons:
        start = text.find(authors, base)
        evidence["authors"] = _span_mappings(positions, start, start + len(authors))
    diagnostics.extend(_clipped_findings(lines, evidence))
    diagnostics.extend(_diacritic_findings(lines, evidence))
    fields = {
        field: _semantic_text(value) if field in {"title", "journal"} else value
        for field, value in fields.items()
    }
    for fragment, line in zip(fragments, lines, strict=True):
        if line.get("_clipped"):
            fragment["clipped"] = True
    pdf = {
        "label": label_value,
        "text": text,
        "fragments": fragments,
        "field_evidence": evidence,
        "uris": uris,
        "diagnostics": diagnostics,
    }
    return {
        "entry": {
            "key": key,
            "type": _entry_type(tail, venue),
            "fields": fields,
            "persons": persons,
        },
        "pdf": pdf,
        "validations": {
            "extraction": {
                "state": "needs_review" if diagnostics else "complete",
                "diagnostics": diagnostics,
            }
        },
    }
