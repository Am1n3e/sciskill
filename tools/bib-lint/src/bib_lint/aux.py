"""Read citation records from compiled BibTeX/natbib auxiliary files."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuxCitations:
    keys: set[str] = field(default_factory=set)
    files: set[Path] = field(default_factory=set)


def read_aux(path: str | Path, *, encoding: str = "utf-8") -> AuxCitations:
    """Follow @input records without executing TeX; cycles are visited only once."""
    root = Path(path).resolve().parent
    result = AuxCitations()

    def visit(source: Path) -> None:
        source = source.resolve()
        if source in result.files:
            return
        result.files.add(source)
        for number, line in enumerate(source.read_text(encoding=encoding).splitlines(), 1):
            if re.match(r"\s*\\abx@aux@", line):
                raise ValueError(f"{source}:{number}: biblatex AUX is not supported")
            command = re.match(r"\s*\\(citation|@input)\b", line)
            if command is None:
                continue
            record = re.fullmatch(r"\s*\\(citation|@input)\{([^{}]*)\}\s*(?:%.*)?", line)
            if record is None:
                raise ValueError(f"{source}:{number}: malformed AUX citation/input record")
            name, value = record.groups()
            if name == "citation":
                result.keys.update(key.strip() for key in value.split(",") if key.strip())
            else:
                if not value.strip():
                    raise ValueError(f"{source}:{number}: empty AUX input path")
                # TeX normally records paths relative to the build root.
                child = root / value.strip()
                if not child.exists():
                    child = source.parent / value.strip()
                visit(child)

    visit(Path(path))
    return result
