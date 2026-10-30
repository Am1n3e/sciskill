"""Resolve exact citation identities before accepting unique Unicode casefold aliases."""

from collections.abc import Iterable
from dataclasses import dataclass


def resolve_citation_key(key: str, known_keys: Iterable[str]) -> str | None:
    """Return one original key, or reject an ambiguous non-exact alias."""
    known = set(known_keys)
    if key in known:
        return key
    matches = sorted(candidate for candidate in known if candidate.casefold() == key.casefold())
    if len(matches) > 1:
        raise ValueError(f"Ambiguous citation key alias {key!r}; matches: {', '.join(matches)}")
    return matches[0] if matches else None


@dataclass(frozen=True)
class CitationUsage:
    used_keys: frozenset[str]
    missing_keys: tuple[str, ...]
    citation_count: int


def resolve_citation_usage(known_keys: Iterable[str], cited_keys: Iterable[str]) -> CitationUsage:
    """Use the same resolution for eligibility, warnings, and unique citation counts."""
    known, cited = frozenset(known_keys), frozenset(cited_keys)
    matched, missing = set(), []
    for key in sorted(cited - {"*"}):
        resolved = resolve_citation_key(key, known)
        if resolved is None:
            missing.append(key)
        else:
            matched.add(resolved)
    return CitationUsage(
        used_keys=known if "*" in cited else frozenset(matched),
        missing_keys=tuple(missing),
        citation_count=len(matched) + len({key.casefold() for key in missing}),
    )
