"""Serializable parsed data, separate from the parsing backend."""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class Name:
    """Name parts retain TeX spelling; ``literal`` means brace-protected, not verified corporate."""

    bibtex: str
    kind: Literal["person", "literal", "others"]
    first: tuple[str, ...]
    middle: tuple[str, ...]
    prelast: tuple[str, ...]
    last: tuple[str, ...]
    lineage: tuple[str, ...]


@dataclass(frozen=True)
class Entry:
    key: str
    type: str
    fields: dict[str, str]
    persons: dict[str, tuple[Name, ...]]


@dataclass(frozen=True)
class Bibliography:
    source_name: str
    source_sha256: str
    source_text: str
    entries: dict[str, Entry]
    preambles: tuple[str, ...]

    def to_dict(self, *, include_source: bool = False, used_keys: set[str] | None = None) -> dict:
        """Return versioned JSON-ready data; retain file order and citation-key spelling."""
        used = None if used_keys is None else {key.lower() for key in used_keys}
        items = [
            {
                "entry": asdict(entry),
                "validations": {}
                if used is None
                else {"is_used": "*" in used or key.lower() in used},
            }
            for key, entry in self.entries.items()
        ]
        result = {
            "summary": {
                "total_count": len(items),
                "total_not_used": None
                if used is None
                else sum(not item["validations"]["is_used"] for item in items),
            },
            "items": items,
            "schema_version": 2,
            "source": {"name": self.source_name, "sha256": self.source_sha256},
            "preambles": list(self.preambles),
        }
        if include_source:
            result["source_text"] = self.source_text
        return result
