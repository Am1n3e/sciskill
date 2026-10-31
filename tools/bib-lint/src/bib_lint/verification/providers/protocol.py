"""Immutable retrieval-only interface. Citation decisions belong to shared matching."""

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from bib_lint.verification.matching import input_record


@dataclass(frozen=True)
class Author:
    given: str = ""
    family: str = ""
    suffix: str = ""
    kind: str = ""


def _author_data(author):
    data = asdict(author)
    if not data["kind"]:
        data.pop("kind")
    return data


@dataclass(frozen=True)
class LookupQuery:
    citation_key: str
    title: str | None = None
    authors: tuple[Author, ...] = ()
    year: str | None = None
    venue: str | None = None
    identifiers: tuple[tuple[str, str], ...] = ()
    input_url: str = ""
    record_type: str = "publication"
    fields: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_entry(cls, entry):
        record = input_record(entry)
        return cls(
            citation_key=entry.get("key", "_unknown"),
            title=record["title"],
            authors=tuple(Author(**a) for a in record["authors"]),
            year=record["year"],
            venue=record["venue"],
            identifiers=tuple(record["identifiers"].items()),
            input_url=entry.get("fields", {}).get("url", ""),
            record_type=record["record_type"],
            fields=tuple(entry.get("fields", {}).items()),
        )

    def as_record(self):
        return {
            "title": self.title,
            "authors": [_author_data(a) for a in self.authors],
            "year": self.year,
            "venue": self.venue,
            "identifiers": dict(self.identifiers),
            "input_url": self.input_url,
            "record_type": self.record_type,
            "input_fields": dict(self.fields),
        }


@dataclass(frozen=True)
class RequestPolicy:
    timeout: float = 20
    interval: float = 1
    backoffs: tuple[float, ...] = (2, 4)
    max_retry_after: float = 10
    max_fetches: int = 10
    max_attempts: int = 30
    max_pages: int = 5
    max_candidates: int = 100
    max_redirects: int = 4

    def validate(self):
        for name in ("timeout", "interval", "max_retry_after"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"Invalid request policy: {name}")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid request policy: {name}")
        for name in ("max_fetches", "max_attempts", "max_pages", "max_candidates", "max_redirects"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"Invalid request policy: {name}")
        if not isinstance(self.backoffs, tuple) or len(self.backoffs) > self.max_attempts:
            raise ValueError("Invalid request policy: backoffs")
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in self.backoffs):
            raise ValueError("Invalid request policy: backoffs")


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    display_name: str
    adapter_version: str
    evidence_category: str
    allowed_hosts: tuple[str, ...]
    canonical_priority: int = 0
    request_policy: RequestPolicy = field(default_factory=RequestPolicy)
    discovery_config: tuple[tuple[str, str], ...] = ()

    def validate(self):
        if not isinstance(self.id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.id):
            raise ValueError("Provider ID must be a stable lowercase identifier")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError(f"Missing display name: {self.id}")
        if not isinstance(self.adapter_version, str) or not self.adapter_version.strip():
            raise ValueError(f"Missing adapter version: {self.id}")
        if self.evidence_category not in {
            "preprint_archive",
            "publication_archive",
            "review_platform",
            "resolver",
        }:
            raise ValueError(f"Invalid evidence category: {self.id}")
        if type(self.canonical_priority) is not int:
            raise ValueError(f"Invalid canonical priority: {self.id}")
        if (
            not isinstance(self.allowed_hosts, tuple)
            or not self.allowed_hosts
            or any(
                not isinstance(h, str) or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", h)
                for h in self.allowed_hosts
            )
        ):
            raise ValueError(f"Invalid allowed hosts: {self.id}")
        if not isinstance(self.request_policy, RequestPolicy):
            raise ValueError(f"Invalid request policy: {self.id}")
        self.request_policy.validate()
        if (
            not isinstance(self.discovery_config, tuple)
            or any(
                not isinstance(p, tuple) or len(p) != 2 or any(not isinstance(v, str) for v in p)
                for p in self.discovery_config
            )
            or len(dict(self.discovery_config)) != len(self.discovery_config)
        ):
            raise ValueError(f"Invalid discovery configuration: {self.id}")

    def serialize(self):
        self.validate()
        data = asdict(self)
        data["allowed_hosts"] = list(self.allowed_hosts)
        data["request_policy"]["backoffs"] = list(self.request_policy.backoffs)
        data["discovery_config"] = dict(self.discovery_config)
        return data


@dataclass(frozen=True)
class Applicability:
    state: str = "applicable"
    reason: str = ""
    strategies: tuple[str, ...] = ()

    def validate(self):
        if self.state not in {"applicable", "inapplicable", "insufficient_context"}:
            raise ValueError("Invalid applicability state")
        if not isinstance(self.reason, str) or not isinstance(self.strategies, tuple):
            raise ValueError("Invalid applicability diagnostic")
        if any(not isinstance(s, str) for s in self.strategies):
            raise ValueError("Invalid lookup strategies")


@dataclass(frozen=True)
class Candidate:
    title: str | None
    authors: tuple[Author, ...] = ()
    year: str | int | None = None
    venue: str | None = None
    identifiers: tuple[tuple[str, str], ...] = ()
    url: str = ""
    record_type: str = "unknown"
    publication_status: str = "unknown"
    version: str | None = None
    provenance: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_record(cls, record, *, provenance=None):
        return cls(
            title=record.get("title"),
            authors=tuple(Author(**a) for a in record.get("authors", [])),
            year=record.get("year") or None,
            venue=record.get("venue") or None,
            identifiers=tuple((k, v) for k, v in record.get("identifiers", {}).items() if v),
            url=record.get("url") or "",
            record_type=record.get("record_type", "unknown"),
            publication_status=record.get("publication_status", "unknown"),
            version=record.get("version"),
            provenance=tuple((provenance or record.get("provenance") or {}).items()),
        )

    def validate(self):
        if any(
            v is not None and not isinstance(v, str) for v in (self.title, self.venue, self.version)
        ):
            raise ValueError("Candidate text fields must be text or unknown")
        if self.year is not None and type(self.year) not in (str, int):
            raise ValueError("Candidate year must be text, integer or unknown")
        if not isinstance(self.authors, tuple) or any(
            not isinstance(a, Author)
            or any(not isinstance(v, str) for v in asdict(a).values())
            or a.kind not in {"", "person", "literal", "others"}
            for a in self.authors
        ):
            raise ValueError("Candidate authors must be ordered structured names")
        for pairs in (self.identifiers, self.provenance):
            if (
                not isinstance(pairs, tuple)
                or any(
                    not isinstance(p, tuple)
                    or len(p) != 2
                    or any(not isinstance(v, str) for v in p)
                    for p in pairs
                )
                or len(dict(pairs)) != len(pairs)
            ):
                raise ValueError("Candidate identifiers/provenance must be immutable text pairs")
        if (
            not self.provenance
            or not isinstance(self.url, str)
            or urlsplit(self.url).scheme != "https"
        ):
            raise ValueError("Candidate needs provenance and a canonical HTTPS URL")
        if self.record_type not in {"preprint", "publication", "unknown"}:
            raise ValueError("Invalid candidate record kind")
        if self.publication_status not in {
            "accepted",
            "published",
            "submitted",
            "rejected",
            "withdrawn",
            "unknown",
        }:
            raise ValueError("Invalid publication status")

    def as_record(self):
        self.validate()
        result = asdict(self)
        result["authors"] = [_author_data(a) for a in self.authors]
        result["identifiers"] = dict(self.identifiers)
        result["provenance"] = dict(self.provenance)
        return result


@dataclass(frozen=True)
class LookupAttempt:
    strategy: str
    scope: str
    query: str = ""
    complete: bool = True
    candidate_urls: tuple[str, ...] = ()
    diagnostic: str = ""


@dataclass(frozen=True)
class LookupResult:
    candidates: tuple[Candidate, ...] = ()
    attempts: tuple[LookupAttempt, ...] = ()
    complete: bool = True
    diagnostic: str = ""
    redirect_url: str | None = None

    def _validate_redirect(self):
        if self.redirect_url is None:
            return
        from bib_lint.verification.input_checks import invalid_url_characters, safe_url

        if not isinstance(self.redirect_url, str):
            raise ValueError("Resolver destination must be a URL")
        parsed = urlsplit(self.redirect_url)
        if (
            self.candidates
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or not safe_url(parsed)
            or invalid_url_characters(self.redirect_url)
        ):
            raise ValueError("A resolver must return a safe URL without invented candidates")

    def validate(self):
        self._validate_redirect()
        if type(self.complete) is not bool or not isinstance(self.diagnostic, str):
            raise ValueError("Invalid lookup completion diagnostic")
        if not isinstance(self.candidates, tuple) or not isinstance(self.attempts, tuple):
            raise ValueError("Lookup results must be immutable")
        for candidate in self.candidates:
            if not isinstance(candidate, Candidate):
                raise ValueError("Lookup must return normalized candidates")
            candidate.validate()
        for attempt in self.attempts:
            if not isinstance(attempt, LookupAttempt) or not attempt.strategy or not attempt.scope:
                raise ValueError("Lookup attempts need a strategy and searched scope")
            if (
                type(attempt.complete) is not bool
                or any(
                    not isinstance(v, str)
                    for v in (attempt.strategy, attempt.scope, attempt.query, attempt.diagnostic)
                )
                or not isinstance(attempt.candidate_urls, tuple)
                or any(not isinstance(v, str) for v in attempt.candidate_urls)
            ):
                raise ValueError("Invalid lookup attempt")
        if self.candidates and not self.attempts:
            raise ValueError("Candidates need lookup provenance")
        if self.complete and any(not a.complete for a in self.attempts):
            raise ValueError("Incomplete attempt cannot claim complete discovery")


class Provider(Protocol):
    descriptor: ProviderDescriptor

    def applicability(self, query: LookupQuery) -> Applicability: ...

    def lookup(self, query: LookupQuery, context: "ProviderContext") -> LookupResult: ...


class ProviderContext(Protocol):
    def get(self, url: str, *, params=None, page=False) -> str: ...

    def json(self, url: str, *, params=None, page=False): ...

    def shortlist(self, candidate: Candidate) -> Candidate: ...
