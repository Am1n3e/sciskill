"""Exact source spans and a deliberately conservative local sentence baseline."""

import hashlib
import re
from bisect import bisect_right

from bib_lint.claims.protocols import Location, Position, Source


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def position(file: str, text: str, offset: int) -> Position:
    starts = [0, *(m.end() for m in re.finditer("\n", text))]
    line = bisect_right(starts, offset)
    return Position(file, line, offset - starts[line - 1] + 1)


def location(source: Source, start: int, end: int) -> Location:
    return Location(
        position(source.file, source.text, start), position(source.file, source.text, end)
    )


def offset(text: str, point: Position) -> int:
    lines = text.splitlines(keepends=True) + [""]
    if type(point.line) is not int or not 1 <= point.line <= len(lines):
        raise ValueError("Claim location has an invalid line")
    line = lines[point.line - 1]
    content = line.rstrip("\r\n")
    if type(point.column) is not int or not 1 <= point.column <= len(content) + 1:
        raise ValueError("Claim location has an invalid column")
    return sum(map(len, lines[: point.line - 1])) + point.column - 1


def diagnostic(code: str, message: str, where: Location | None = None) -> dict:
    result = {"code": code, "message": message}
    if where is not None:
        result["location"] = where.to_dict()
    return result
