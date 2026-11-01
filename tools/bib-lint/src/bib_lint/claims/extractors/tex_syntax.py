"""Bounded lexical TeX inspection; never expands macros or executes commands."""

import re
from dataclasses import dataclass

COMMAND = re.compile(r"\\([a-zA-Z@]+|.)", re.S)
LITERAL = re.compile(r"\\begin\{(verbatim\*?|lstlisting|minted|comment)\}")
VERB = re.compile(r"\\verb\*?([^a-zA-Z\s])")
DEFINITION = re.compile(r"\\(?:newcommand|renewcommand|providecommand|def)\b")


def _blank(text: str) -> str:
    return "".join(c if c in "\r\n" else " " for c in text)


def group(text: str, start: int, opening="{", closing="}") -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start == len(text) or text[start] != opening:
        raise ValueError("Expected a literal TeX argument")
    depth, cursor = 1, start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        depth += (char == opening) - (char == closing)
        cursor += 1
        if depth == 0:
            return text[start + 1 : cursor - 1], cursor
    raise ValueError("Unclosed TeX argument")


def visible_text(text: str) -> str:
    """Mask ignored regions without changing any original source offsets."""
    output, cursor = [], 0
    while cursor < len(text):
        end = _ignored_end(text, cursor)
        if end is not None:
            output.append(_blank(text[cursor:end]))
            cursor = end
        elif text[cursor] == "\\":
            match = COMMAND.match(text, cursor)
            output.append(match.group())
            cursor = match.end()
        else:
            output.append(text[cursor])
            cursor += 1
    return "".join(output)


def _ignored_end(text: str, cursor: int) -> int | None:
    if text[cursor] == "%":
        end = text.find("\n", cursor)
        return len(text) if end < 0 else end
    literal = LITERAL.match(text, cursor)
    if literal:
        marker = "\\end{" + literal[1] + "}"
        end = text.find(marker, literal.end())
        return len(text) if end < 0 else end + len(marker)
    verb = VERB.match(text, cursor)
    if verb:
        end = text.find(verb[1], verb.end())
        return len(text) if end < 0 else end + 1
    definition = DEFINITION.match(text, cursor)
    if definition:
        return _definition_end(text, definition.end())
    return None


def _definition_end(text: str, cursor: int) -> int:
    # newcommand's braced command name precedes its body; def's does not.
    first = text.find("{", cursor)
    if first < 0:
        return len(text)
    value, end = group(text, first)
    if re.fullmatch(r"\\[a-zA-Z@]+", value.strip()):
        first = text.find("{", end)
        if first >= 0:
            _, end = group(text, first)
    return end


@dataclass(frozen=True)
class Command:
    name: str
    value: str
    start: int
    end: int


def commands(text: str):
    cursor = 0
    while match := COMMAND.search(text, cursor):
        cursor = match.end()
        name = match[1]
        if name not in {"input", "include", "bibliography", "addbibresource", "nocite"} and not (
            name.startswith("cite") or name in {"autocite", "parencite", "textcite"}
        ):
            continue
        try:
            value, cursor = _argument(text, cursor)
        except ValueError:
            yield Command(name, "", match.start(), cursor)
            continue
        yield Command(name, value, match.start(), cursor)


def _argument(text: str, cursor: int) -> tuple[str, int]:
    if cursor < len(text) and text[cursor] == "*":
        cursor += 1
    for _ in range(3):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "[":
            _, cursor = group(text, cursor, "[", "]")
        else:
            return group(text, cursor)
    raise ValueError("Too many TeX optional arguments")
