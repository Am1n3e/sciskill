"""Independent physical reference anchors from native TeX PDF character runs.

No product parsing, layout or extraction result participates in this gold. Native
hyperref destinations locate an occurrence; decoded renderer bodies identify its
first text run. The runs use PDF content-stream order, preserving TeX columns.
"""

import re
import unicodedata
from statistics import median

import pdfplumber
from pypdf import PdfReader


def _normalized(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum() or c == "?"
    )


def _runs(page):
    runs = []
    for char in page.chars:
        if not char["text"].strip():
            # Keep spaces inside an existing run, but never start a run with one.
            if runs:
                runs[-1].append(char)
            continue
        if (
            not runs
            or abs(char["top"] - runs[-1][0]["top"]) > 2
            or char["x0"] < runs[-1][-1]["x0"] - 1
        ):
            runs.append([])
        runs[-1].append(char)
    cleaned = []
    for run in runs:
        size = median(c["size"] for c in run)
        for index, char in enumerate(run[1:], 1):
            if (
                char["x0"] - run[index - 1]["x1"] > 20
                and char["size"] < max(c["size"] for c in run) * 0.95
                and all(c["text"].isdigit() or c["text"].isspace() for c in run[index:])
            ):
                run = run[:index]
                break
        cleaned.append([c for c in run if not (c["text"].isdigit() and c["size"] < size * 0.9)])
    return [run for run in cleaned if any(c["text"].strip() for c in run)]


def _text(run):
    output, previous = [], None
    for char in run:
        if previous and char["x0"] - previous["x1"] > max(1, char["size"] * 0.15):
            output.append(" ")
        output.append(char["text"])
        previous = char
    return " ".join("".join(output).split())


def _matches(run, body):
    text = _text(run)
    expected = _normalized(body)
    alternatives = [text, re.sub(r"^\s*(?:\[[^]]+\]|\d+\.)\s*", "", text)]
    # Native line wrapping may end on a discretionary hyphen; normalization
    # removes it while retaining the independent renderer's letters and order.
    return any(
        candidate and expected.startswith(candidate[: min(len(candidate), 48)])
        for candidate in map(_normalized, alternatives)
    )


def _anchor(page, run):
    chars = [char for char in run if char["text"].strip()]
    return {
        "page": page,
        "box": [
            round(value, 3)
            for value in (
                min(c["x0"] for c in chars),
                min(c["top"] for c in chars),
                max(c["x1"] for c in chars),
                max(c["bottom"] for c in chars),
            )
        ],
        "text": _text(run),
    }


def _bodies(project):
    # Import lazily: the existing independent BBL decoder can itself use this
    # module while constructing its rendered-source expectations.
    from .oracles import bibliography_bodies, rendered_text

    return {
        key: rendered_text(body)[0]
        for key, body in bibliography_bodies((project / "main.bbl").read_text())
    }


def page_anchors(project, ordered_keys, bodies=None):
    """Return tight first-visible-line anchors, omitting unprinted empty items.

    ``bodies`` maps native build keys to decoded renderer text, never canonical
    source metadata. A nonempty body that cannot be anchored is an oracle error.
    """
    bodies = _bodies(project) if bodies is None else bodies
    reader = PdfReader(project / "main.pdf")
    destinations = reader.named_destinations
    with pdfplumber.open(project / "main.pdf") as document:
        lines = [(page.page_number, run) for page in document.pages for run in _runs(page)]
        heights = {page.page_number: page.height for page in document.pages}
    heading = next(
        (
            i
            for i, (_, run) in enumerate(lines)
            if _normalized(_text(run)) in {"references", "bibliography"}
        ),
        -1,
    )
    cursor, result = heading + 1, {}
    for key in ordered_keys:
        body = bodies[key]
        destination = destinations.get("cite." + key)
        if destination:
            page = reader.get_destination_page_number(destination) + 1
            top = heights[page] - float(destination["/Top"])
            left = float(destination["/Left"])
            candidates = [
                (i, run)
                for i, (number, run) in enumerate(lines)
                if number == page
                and -12 <= run[0]["top"] - top <= 16
                and min(c["x0"] for c in run) >= left - 2
            ]
        else:
            candidates = [(i, run) for i, (_, run) in enumerate(lines) if i >= cursor]
        found = next(((i, run) for i, run in candidates if _matches(run, body)), None)
        if not body.strip():
            found = next(
                ((i, run) for i, run in candidates if re.fullmatch(r"\[[^]]+\]|\d+\.", _text(run))),
                None,
            )
            if not destination:
                continue
        if found is None:
            if not body.strip():
                continue
            raise ValueError(f"Cannot independently anchor native bibliography item {key}")
        index, run = found
        result[key] = _anchor(lines[index][0], run)
        cursor = index + 1
    return result
