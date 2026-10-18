"""Coordinate independent BibTeX and AUX parsing into a single JSON report."""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from bib_lint.aux import read_aux
from bib_lint.parser import parse_file
from bib_lint.storage import report_lock, report_paths
from bib_lint.storage import write_json as _write_json


@dataclass
class StepResult:
    output: Path
    total: int | None = None
    unused: int | None = None
    missing: list[str] = field(default_factory=list)
    error: str | None = None


def _protect(output: Path, inputs: Iterable[Path]) -> None:
    for source in inputs:
        if output.resolve() == source.resolve() or (
            output.exists() and source.exists() and output.samefile(source)
        ):
            raise ValueError(f"JSON output must not overwrite the input file: {source}")


def parse_bib(
    bib_file: str | Path,
    aux_file: str | Path | None = None,
    *,
    output: str | Path | None = None,
    encoding: str = "utf-8",
    include_source: bool = False,
) -> tuple[StepResult, StepResult | None]:
    """Parse both inputs independently, then atomically write one combined report."""
    source = Path(bib_file)
    destination = Path(output) if output is not None else source.with_suffix(".json")
    final, checkpoint = report_paths(destination)
    bib = StepResult(checkpoint)
    aux = None
    try:
        _protect(final, [source])
        _protect(checkpoint, [source])
        bibliography = parse_file(source, encoding=encoding)
        bib.total = len(bibliography.entries)
    except (OSError, ValueError, LookupError) as exc:
        bib.error = str(exc)
        return bib, aux

    citations = None
    if aux_file is not None:
        aux = StepResult(checkpoint)
        try:
            citations = read_aux(aux_file, encoding=encoding)
            _protect(final, citations.files)
            _protect(checkpoint, citations.files)
            cited = {key.lower() for key in citations.keys}
            known = {key.lower() for key in bibliography.entries}
            aux.total = len(cited - {"*"})
            aux.unused = 0 if "*" in cited else len(known - cited)
            aux.missing = sorted(key for key in citations.keys if key.lower() not in known | {"*"})
        except (OSError, ValueError, LookupError) as exc:
            aux.error = str(exc)
            return bib, aux

    try:
        with report_lock(final):
            if checkpoint.exists() and "verification_run" in json.loads(checkpoint.read_text()):
                raise ValueError(f"Verification checkpoint exists; resume it: {checkpoint}")
            _write_json(
                checkpoint,
                bibliography.to_dict(
                    include_source=include_source,
                    used_keys=None if citations is None else citations.keys,
                ),
            )
    except (OSError, ValueError) as exc:
        bib.error = str(exc)
    return bib, aux
