"""Shared retrieval utilities; identity policy remains in matching."""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pybtex.database import parse_string

from bib_lint.verification.http import LookupFailure
from bib_lint.verification.matching import (
    doi,
    identity_match,
    name_parts,
    normalize,
    title_similarity,
)
from bib_lint.verification.providers.protocol import Candidate, LookupAttempt, LookupResult


class LookupBuilder:
    def __init__(self, context):
        self.context = context
        self.candidates = []
        self.attempts = []
        self.complete = True
        self.diagnostic = ""

    def run(self, strategy, scope, query, retrieve):
        urls = []
        complete, diagnostic = True, ""
        try:
            for candidate in retrieve():
                if candidate not in self.candidates:
                    self.candidates.append(self.context.shortlist(candidate))
                urls.append(candidate.url)
        except LookupFailure as exc:
            diagnostic = str(exc)
            if exc.code != "not_found":
                complete = self.complete = False
                self.diagnostic = diagnostic
            if exc.code not in {"not_found", "incomplete_search"}:
                raise
        except Exception as exc:
            complete = False
            diagnostic = type(exc).__name__
            raise
        finally:
            self.attempts.append(
                LookupAttempt(strategy, scope, query, complete, tuple(urls), diagnostic)
            )
            self.context.lookup_attempts = tuple(self.attempts)
            self.context.retrieved_candidates = tuple(self.candidates)
        return self.complete

    def result(self):
        return LookupResult(
            tuple(self.candidates), tuple(self.attempts), self.complete, self.diagnostic
        )


def direct_matches(query, candidates):
    return bool(candidates) and (
        not query.title or any(identity_match(query.as_record(), c.as_record()) for c in candidates)
    )


def source_identifier(query, name, *aliases):
    fields = dict(query.fields)
    for key in (name, *aliases):
        if fields.get(key):
            return fields[key]
    if normalize(fields.get("archiveprefix")) == normalize(name):
        return fields.get("eprint")
    return None


def supported_url(query, hosts):
    parsed = urlsplit(query.input_url)
    if parsed.hostname in hosts:
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 80, 443}
        ):
            raise LookupFailure("unsupported_url", "Nonstandard source URL")
        if parsed.path.lower().endswith(".pdf"):
            return None
        return query.input_url
    return None


def html(text):
    soup = BeautifulSoup(text, "html.parser")
    if not soup.find():
        raise LookupFailure("invalid_response", "Source did not return an HTML catalog or record")
    return soup


def citation_candidate(text, url, identifiers=None):
    soup = html(text)
    metadata = {}
    for tag in soup.find_all("meta"):
        key = tag.get("name", "").lower()
        metadata.setdefault(key, []).append(tag.get("content", ""))

    def first(*names):
        return next((v for name in names for v in metadata.get(name, []) if v), None)

    title = first("citation_title")
    if not title:
        return None
    date = first("citation_publication_date", "citation_date")
    year = re.search(r"\b(\d{4})\b", date or "")
    ids = dict(identifiers or {})
    if first("citation_doi"):
        ids["doi"] = doi(first("citation_doi"))
    return Candidate.from_record(
        {
            "title": title,
            "authors": [name_parts(v) for v in metadata.get("citation_author", []) if v],
            "year": year[1] if year else None,
            "venue": first("citation_conference_title", "citation_journal_title"),
            "identifiers": ids,
            "url": url.replace("http://", "https://", 1),
            "record_type": "publication",
            "publication_status": "published",
        },
        provenance={
            "source": url,
            "metadata": "citation_meta",
            "publication_status": "archive_record",
        },
    )


def bibtex_candidate(text, url, identifiers=None):
    data = parse_string(text, "bibtex")
    if not data.entries:
        return None
    entry = next(iter(data.entries.values()))
    fields = entry.fields
    return Candidate.from_record(
        {
            "title": fields.get("title"),
            "authors": [name_parts(str(p)) for p in entry.persons.get("author", [])],
            "year": fields.get("year"),
            "venue": fields.get("booktitle") or fields.get("journal"),
            "identifiers": {
                **(identifiers or {}),
                **({"doi": doi(fields["doi"])} if fields.get("doi") else {}),
            },
            "url": url,
            "record_type": "publication",
            "publication_status": "published",
        },
        provenance={
            "source": url,
            "metadata": "source_bibtex",
            "publication_status": "archive_record",
        },
    )


def years(query):
    if query.year and re.fullmatch(r"\d{4}", str(query.year)):
        year = int(query.year)
        return (year, year - 1, year + 1)
    return ()


def catalog_links(text, url, predicate):
    soup = html(text)
    seen = set()
    for anchor in soup.find_all("a", href=True):
        target = urljoin(url, anchor["href"])
        if target in seen or not predicate(target):
            continue
        seen.add(target)
        parent = anchor.find_parent(["li", "tr", "p"]) or anchor.parent
        yield target, anchor.get_text(" ", strip=True), parent.get_text(" ", strip=True)


def shortlisted(query, text, identifier=""):
    if identifier and identifier in text:
        return True
    return bool(query.title) and title_similarity({"title": query.title}, {"title": text}) >= 0.75
