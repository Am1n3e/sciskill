"""Parse without writing, looking up, or correcting bibliographic data."""

import hashlib
from pathlib import Path

from pybtex.database import Person
from pybtex.database.input.bibtex import Parser
from pybtex.exceptions import PybtexError

from bib_lint.models import Bibliography, Entry, Name


class BibliographyParseError(ValueError):
    """Invalid BibTeX or input encoding, with its source and available line number."""

    def __init__(self, source: str, message: str, *, line: int | None = None):
        self.source = source
        self.message = message
        self.line = line
        super().__init__(f"{source}: {message}")


class _Parser(Parser):
    def handle_error(self, error: PybtexError) -> None:
        # The default backend can be configured elsewhere to log and skip errors.
        raise error

    def process_entry(self, entry_type, key, fields) -> None:
        if key in self.data.entries:
            # Pybtex considers citation keys case-insensitively; never lose one silently.
            raise PybtexError(f"repeated bibliography entry: {key}")
        super().process_entry(entry_type, key, fields)


def _name(person: Person) -> Name:
    bibtex = str(person)
    kind = "person"
    if bibtex == "others":
        kind = "others"
    elif (
        not (
            person.first_names
            or person.middle_names
            or person.prelast_names
            or person.lineage_names
        )
        and len(person.last_names) == 1
        and bibtex.startswith("{")
        and bibtex.endswith("}")
    ):
        kind = "literal"
    return Name(
        bibtex=bibtex,
        kind=kind,
        first=tuple(person.first_names),
        middle=tuple(person.middle_names),
        prelast=tuple(person.prelast_names),
        last=tuple(person.last_names),
        lineage=tuple(person.lineage_names),
    )


def _parse(text: str, *, source_name: str, source_sha256: str) -> Bibliography:
    parser = _Parser()
    parser.filename = source_name
    try:
        data = parser.parse_string(text)
    except PybtexError as exc:
        raise BibliographyParseError(
            source_name, str(exc), line=getattr(exc, "lineno", None)
        ) from exc
    entries = {
        key: Entry(
            key=key,
            type=entry.type.lower(),
            fields={field.lower(): value for field, value in entry.fields.items()},
            persons={
                role.lower(): tuple(_name(person) for person in people)
                for role, people in entry.persons.items()
            },
        )
        for key, entry in data.entries.items()
    }
    return Bibliography(
        source_name=source_name,
        source_sha256=source_sha256,
        source_text=text,
        entries=entries,
        preambles=tuple(data.preamble_list),
    )


def parse_string(text: str, *, source_name: str = "<string>") -> Bibliography:
    """Parse Unicode BibTeX. The digest covers the UTF-8 encoding of the supplied text."""
    return _parse(
        text,
        source_name=source_name,
        source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def parse_file(path: str | Path, *, encoding: str = "utf-8") -> Bibliography:
    """Read a file once; the digest covers its original bytes, before decoding."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode(encoding)
    except (UnicodeError, LookupError) as exc:
        raise BibliographyParseError(str(path), f"cannot decode using {encoding}: {exc}") from exc
    return _parse(text, source_name=str(path), source_sha256=hashlib.sha256(raw).hexdigest())
