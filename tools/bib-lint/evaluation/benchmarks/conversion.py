"""Format adapters only: never query sources or use benchmark labels to parse inputs."""

import json
import re
from dataclasses import asdict

from pybtex.database import Person

from bib_lint.models import Bibliography, Entry
from bib_lint.parser import _name
from evaluation.benchmarks.common import digest

CONVERSION_VERSION = 2


def _authors(raw, *, apa=False):
    if apa:
        matches = list(re.finditer(r"([^,]+),\s*((?:[A-Z]\.(?:\s|-)?)+)", raw))
        if matches:
            names, cursor = [], 0
            for match in matches:
                gap = raw[cursor : match.start()].strip(", &")
                if gap:
                    names.append("{" + gap + "}")
                names.append(f"{match[1].strip().lstrip('& ')}, {match[2].strip()}")
                cursor = match.end()
            remainder = raw[cursor:].strip(", &")
            if remainder:
                names.append("others" if remainder in {"…", "et al."} else "{" + remainder + "}")
            return " and ".join(names)
        if "," in raw:
            raise ValueError("Cannot reliably separate APA author names")
        return "{" + raw.strip().rstrip(".") + "}"
    author = re.sub(r",?\s+(?:and|&)\s+", " and ", raw)
    author = re.sub(r",\s+", " and ", author)
    return re.sub(r"(?:and\s+)?et\s+al\.?$", "and others", author, flags=re.I)


def parse_raw_reference(raw):
    """Extract two common citation styles; reject structures we cannot identify.

    Keep original text and extracted fields in conversion.json. This is an explicitly
    limited harness input adapter, not an official benchmark parser or a correction.
    """
    text = " ".join(raw.split())
    # Some published exports use '?' as quotation marks. Recognize that only at
    # explicit author/title and title/venue boundaries, preserving internal '?'.
    quoted = re.match(
        r'^(.*?)\.\s+["“?](.+)["”?]\.?\s*(?:en\.\s*)?((?:In[: ]).*)$', text
    ) or re.match(r'^(.*?)\s*,\s*["“]([^"”]+)["”]\s*,?\s*(.*)$', text)
    apa = re.match(r"^(.*?)\s*\(((?:19|20)\d{2})[^)]*\)\.\s*(.+)$", text)
    acl = re.match(r"^(.*?)\.\s+((?:19|20)\d{2})[a-z]?\.\s+(.+)$", text)
    boundary_pattern = r"(?<![A-Z])\.(?:\s+|(?=[A-Z](?:[a-z]|\s+[a-z])))"
    parts = _citation_parts(text, apa, acl, quoted, boundary_pattern)
    if isinstance(parts, dict):
        return "misc", parts
    authors, year, rest, apa = parts
    author = _authors(authors, apa=bool(apa) or bool(re.search(r",\s*[A-Z]\.\s*,", authors)))
    if not apa and not acl:
        before_identifiers = re.split(
            r"https?://|\b(?:doi|issn|isbn)\s*:|\bvisited on\b", rest, flags=re.I
        )[0]
        years = re.findall(r"(?<![\d.])(?:19|20)\d{2}(?!\d)", before_identifiers)
        year = years[-1] if years else None
    # A title is the first complete sentence after the author/year block. URLs
    # are not part of the title. Ambiguous abbreviation/decimal titles are logged.
    rest = re.split(r"\s+https?://|\s+URL\b|\s+doi\s*:", rest, maxsplit=1, flags=re.I)[0].strip()
    parts = re.split(r"[.?]\s+(?=(?:In\b|Proceedings\b|arXiv\b|[A-Z]))", rest, maxsplit=1)
    title = parts[0].rstrip(". ")
    if not apa:
        # IEEE-style entries may end their title with a comma followed by year.
        title = re.sub(r"(?:,\s*|\.\s+)(?:19|20)\d{2}\.?$", "", title)
    if not title or not author:
        raise ValueError("Empty title or author extraction")
    fields = {"title": title, "author": author}
    if year:
        fields["year"] = year
    kind = _venue_fields(parts, fields)
    # Hosting on arXiv does not justify replacing the venue claimed in a citation.
    if re.search(r"\barXiv\b", rest, re.I):
        venue = fields.get("journal", "")
        if not fields.get("booktitle") and (not venue or "arxiv" in venue.lower()):
            kind = "article"
            fields["journal"] = "arXiv"
    _identifier_fields(text, fields)
    return kind, fields


def make_report(case):
    if case.fields is None:
        kind, fields = parse_raw_reference(case.raw_reference)
        method = "limited_raw_citation_adapter"
    else:
        kind, fields = case.bibtex_type, dict(case.fields)
        method = "official_structured_fields"
    author = fields.get("author", "")
    # Person normalizes name formatting, but does not look up/correct identities.
    names = tuple(
        _name(Person(part.strip())) for part in re.split(r"\s+and\s+", author) if part.strip()
    )
    entry = Entry(
        case.id,
        kind,
        {k: v for k, v in fields.items() if k != "author"},
        {"author": names} if names else {},
    )
    raw = case.raw_reference or json.dumps(case.fields, sort_keys=True)
    bibliography = Bibliography(case.id, digest(raw.encode()), raw, {case.id: entry}, ())
    report = bibliography.to_dict()
    report["schema_version"] = 3
    report["verification_scope"] = {"mode": "all", "eligible_keys": [case.id]}
    conversion = {
        "version": CONVERSION_VERSION,
        "method": method,
        "raw_reference": case.raw_reference,
        "raw_sha256": digest(raw.encode()),
        "fields": fields,
        "entry": asdict(entry),
    }
    return report, conversion


def _venue_fields(parts, fields):
    kind = "misc"
    if len(parts) > 1:
        venue = re.sub(r"^In[: ]+", "", parts[1])
        # Editors, publication year, volume and publisher/address prose are
        # separate citation components rather than part of a venue's name.
        venue = re.sub(r"^.*?\((?:eds?\.|editors?)\),?\s*", "", venue, flags=re.I)
        venue = re.sub(r"\.\s+(?:19|20)\d{2}\.?$", "", venue)
        venue = re.split(
            r"\.\s+(?:Association for|European Language|Publisher:|Ed\. by)", venue, maxsplit=1
        )[0]
        venue = re.split(r",\s*(?:pages|pp?\.|volume|\d)|\s+doi:", venue, maxsplit=1)[0]
        venue = re.sub(r"\s*\((?:[A-Za-z. ]*\s)?(?:19|20)\d{2}\).*", "", venue)
        venue = venue.strip().rstrip(".")
        if venue:
            conference = bool(re.search(r"Proceedings|Conference|Workshop", venue))
            if not conference:
                volume = re.search(r"\s+(\d+)(?:\.(\d+)|\((\d+)\))?$", venue)
                if volume:
                    fields["volume"] = volume[1]
                    if volume[2] or volume[3]:
                        fields["number"] = volume[2] or volume[3]
                    venue = venue[: volume.start()].rstrip()
            kind = "inproceedings" if conference else "article"
            fields["booktitle" if conference else "journal"] = venue
    return kind


def _identifier_fields(text, fields):
    url = re.search(r"https?://\S+", text)
    if url:
        fields["url"] = url.group().rstrip(".,")
    doi = re.search(r"(?:doi\s*:\s*|doi\.org/)(10\.\d{4,9}/\S+)", text, re.I)
    if doi:
        fields["doi"] = doi.group(1).rstrip(".,")
    arxiv = re.search(
        r"(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.[\dXx]+(?:v\d+)?)", text, re.I
    )
    if arxiv:
        fields["eprint"] = arxiv.group(1)
        fields["archiveprefix"] = "arXiv"


def _citation_parts(text, apa, acl, quoted, boundary_pattern):
    year = None
    if apa and re.search(boundary_pattern, apa[1].rstrip(". ")):
        apa = None
    if acl:
        authors, year, rest = acl.groups()
        apa = None
    elif quoted:
        authors, title, tail = quoted.groups()
        rest = title.rstrip(", ") + ". " + tail
        apa = None
    elif apa:
        authors, year, rest = apa.groups()
        if rest.startswith(("https://", "http://")):
            # Standards sometimes put the title before the parenthesized year,
            # with no author. Preserve that absence rather than invent a creator.
            return {"title": authors.strip(), "year": year, "url": rest.rstrip("., ")}
    else:
        springer = re.match(r"^(.*[A-Z]\.):\s+(.+)$", text)
        if springer:
            authors, rest = springer.groups()
        else:
            boundary = re.search(boundary_pattern, text)
            if boundary is None:
                raise ValueError("Cannot identify author/title boundary")
            authors, rest = text[: boundary.start()], text[boundary.end() :]
    return authors, year, rest, apa
