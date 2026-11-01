"""The extraction and scientific-validation boundaries."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Position:
    file: str
    line: int
    column: int


@dataclass(frozen=True)
class Location:
    start: Position
    end: Position
    pdf_regions: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        value = {"start": asdict(self.start), "end": asdict(self.end)}
        if self.pdf_regions:
            value["pdf_regions"] = list(self.pdf_regions)
        return value


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claim: str
    location: Location


@dataclass(frozen=True)
class Validation:
    result: Literal["valid", "invalid", "unresolved"]
    details: str

    def to_dict(self) -> dict:
        if (
            self.result not in {"valid", "invalid", "unresolved"}
            or not isinstance(self.details, str)
            or not self.details.strip()
        ):
            raise ValueError("Validator must return valid/invalid/unresolved and nonempty details")
        return asdict(self)


@dataclass(frozen=True)
class Request:
    path: Path
    bibliographies: tuple[Path, ...] = ()
    project_root: Path | None = None
    model: str | None = None


@dataclass(frozen=True)
class CitationOccurrence:
    citation_id: str
    text: str
    location: Location
    keys: tuple[str, ...]
    document_occurrence: int = 0


@dataclass(frozen=True)
class Source:
    file: str
    path: Path
    raw: bytes
    text: str
    snapshot: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Extraction:
    document: dict
    sources: list[Source]
    citations: dict[str, list[Claim]]
    diagnostics: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    extractor: dict = field(default_factory=lambda: {"id": "unknown", "version": "unknown"})
    occurrences: list[CitationOccurrence] = field(default_factory=list)


@runtime_checkable
class Extractor(Protocol):
    def extract(self, request: Request) -> Extraction: ...


@runtime_checkable
class Validator(Protocol):
    def validate(self, claim: Claim, citation_key: str) -> Validation: ...
