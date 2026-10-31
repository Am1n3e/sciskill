"""Recover reference occurrences from text geometry, independent of citation metadata."""

import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from statistics import median

HEADING = re.compile(
    r"^(?:(?:\d+|[A-Z])\.?\s+)?(?:references|bibliography|literature cited)$", re.I
)
LABEL = re.compile(r"^\s*(?:\[([^\]\n]{1,120})\]|(\d+)\.(?=\s|$))\s*")


def _word_style(word):
    return word["fontname"], round(word["size"], 1)


def _line_numbers(words, known_styles=None):
    styles = known_styles if known_styles is not None else set()
    groups = defaultdict(list)
    body = Counter(_word_style(word) for word in words if not word["text"].isdigit())
    body_style = body.most_common(1)[0][0] if body else None
    for word in words:
        if word["text"].isdigit() and len(word["text"]) <= 4:
            groups[round(word["x1"] / 3)].append(word)
    for group in groups.values():
        numbers = [int(word["text"]) for word in sorted(group, key=lambda word: word["top"])]
        if (
            len(numbers) >= 4
            and sum(b == a + 1 for a, b in zip(numbers, numbers[1:], strict=False))
            >= len(numbers) * 0.65
        ):
            if all(1800 <= number <= 2099 for number in numbers):
                continue
            for word in group:
                style = _word_style(word)
                styles.add(style if style != body_style else (*style, round(word["x1"] / 3)))
    return [
        word
        for word in words
        if not (
            word["text"].isdigit()
            and (
                _word_style(word) in styles or (*_word_style(word), round(word["x1"] / 3)) in styles
            )
        )
    ]


def _gutter(words, width):
    """A column gutter has vertically overlapping text on both sides but little ink."""
    if len(words) < 30:
        return None
    starts = sorted(word["x0"] for word in words)
    ends = sorted(word["x1"] for word in words)
    low = max(width * 0.12, starts[0] + 30)
    high = min(width * 0.88, ends[-1] - 30)
    candidates = [
        g
        for g in range(int(low), int(high), 3)
        if bisect_right(ends, g) >= 10 and len(starts) - bisect_left(starts, g) >= 10
    ]
    if not candidates:
        return None

    def ink(gutter):
        return bisect_left(starts, gutter + 5) - bisect_right(ends, gutter - 5)

    gutter = min(candidates, key=lambda g: (ink(g), abs(g - width / 2)))
    left = [w for w in words if w["x1"] < gutter]
    right = [w for w in words if w["x0"] > gutter]
    crossing = ink(gutter)
    rows = len({round(w["top"] / 6) for w in words})
    if min(len(left), len(right)) < 10 or crossing > max(2, rows * 0.18):
        return None
    overlap = min(max(w["bottom"] for w in left), max(w["bottom"] for w in right)) - max(
        min(w["top"] for w in left), min(w["top"] for w in right)
    )
    return gutter if overlap > 50 else None


def _rows(words):
    rows = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(word["top"] - rows[-1][0]["top"]) < 3:
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def _row(words, page, column):
    words = sorted(words, key=lambda w: w["x0"])
    text, spans, previous = "", [], None
    for word in words:
        if previous and word["x0"] - previous["x1"] > 0.7:
            text += " "
        start = len(text)
        text += word["text"]
        spans.append(
            {"start": start, "end": len(text), "font": word["fontname"], "size": word["size"]}
        )
        previous = word
    return {
        "page": page,
        "x0": min(w["x0"] for w in words),
        "top": min(w["top"] for w in words),
        "x1": max(w["x1"] for w in words),
        "bottom": max(w["bottom"] for w in words),
        "text": text,
        "_spans": spans,
        "_column": column,
    }


def _without_numbered_headers(words, page):
    removed = set()
    for row in _rows(words):
        if len(row) < 2 or row[0]["top"] >= page.height * 0.15:
            continue
        ends = (
            (row[0], row[1]["x0"] - row[0]["x1"]),
            (row[-1], row[-1]["x0"] - row[-2]["x1"]),
        )
        if any(
            number["text"] == str(page.page_number) and gap > max(12, number["size"] * 2)
            for number, gap in ends
        ):
            removed.update(id(word) for word in row)
    return [word for word in words if id(word) not in removed]


def page_lines(page, number_styles=None):
    words = page.extract_words(
        x_tolerance=1.5, y_tolerance=2, extra_attrs=["fontname", "size"], expand_ligatures=False
    )
    words = _line_numbers(
        [
            word
            for word in words
            if 20 < word["top"] < page.height - 35
            and not (
                word["text"] == str(page.page_number)
                and word["top"] > page.height * 0.8
                and abs((word["x0"] + word["x1"]) / 2 - page.width / 2) < 18
            )
        ],
        number_styles,
    )
    words = _without_numbered_headers(words, page)
    gutter = _gutter(words, page.width)
    columns = (
        [[w for w in words if (w["x0"] >= gutter) == bool(side)] for side in (0, 1)]
        if gutter
        else [words]
    )
    lines = [
        _row(row, page.page_number, column)
        for column, group in enumerate(columns)
        for row in _rows(group)
    ]
    for line in lines:
        line["_width"] = page.width
        line["_clipped"] = line["x0"] < 0 or line["x1"] > page.width
        line["x0"] = max(0, min(page.width, line["x0"]))
        line["x1"] = max(0, min(page.width, line["x1"]))
    return lines


def _end(line):
    text = line["text"]
    heading = re.match(
        r"^(?:Appendix\b|[A-Z](?:\.|\s)\s*\w|Supplementary\b|Acknowledg|.*Checklist\b)", text, re.I
    )
    bold = any(re.search(r"bold|cmbx|medi|demi", s["font"], re.I) for s in line["_spans"])
    citation_like = bool(re.search(r"\b(?:18|19|20)\d{2}\b|https?://", text)) or text.count(".") > 1
    return bool(heading and bold and len(text) < 140 and not citation_like)


def _without_headers(pages):
    headers = []
    for page in pages:
        grouped = defaultdict(list)
        for line in page:
            if line["top"] < 80:
                grouped[round(line["top"] / 3)].append(line)
        for group in grouped.values():
            text = " ".join(line["text"] for line in sorted(group, key=lambda line: line["x0"]))
            headers.append((text, group))
    running = Counter(text for text, _ in headers)
    removed = set()
    for text, group in headers:
        width = group[0].get("_width", 612)
        centered = (
            min(line["x0"] for line in group) > width * 0.22
            and max(line["x1"] for line in group) < width * 0.78
            and group[0]["top"] < 60
        )
        if (
            (running[text] > 1 or centered)
            and (
                not re.search(r"[.!?]", text)
                or re.search(r"confidential|review\s*copy|under\s*review", text, re.I)
            )
            and not HEADING.fullmatch(text)
        ):
            removed.update(id(line) for line in group)
    return [line for page in pages for line in page if id(line) not in removed]


def bibliography_lines(pages):
    lines = _without_headers(pages)
    headings = [
        index for index, line in enumerate(lines) if HEADING.fullmatch(line["text"].strip())
    ]
    if not headings:
        raise ValueError(
            "No identifiable bibliography heading; a readable reference list is needed"
        )
    selected, diagnostics, active = [], [], False
    for line in lines[headings[0] :]:
        if HEADING.fullmatch(line["text"].strip()):
            active = True
            continue
        if _end(line):
            active = False
        if active:
            selected.append(line)
    if len(headings) > 1:
        diagnostics.append(
            {
                "code": "multiple_bibliographies",
                "message": "Multiple bibliography sections require coverage review",
            }
        )
    return selected, diagnostics


def _label(line):
    match = LABEL.match(line["text"])
    if (
        match
        and match[2]
        and re.match(r"(?:URL|doi:|https?://)", line["text"][match.end() :], re.I)
    ):
        return None
    return match


def _wrap_gap(lines):
    gaps = [
        right["top"] - left["bottom"]
        for left, right in zip(lines, lines[1:], strict=False)
        if left["page"] == right["page"]
        and left["_column"] == right["_column"]
        and 0 <= right["top"] - left["bottom"] < 15
    ]
    return median(gaps) + 1 if gaps else 4


def occurrences(lines):
    bases = defaultdict(list)
    for line in lines:
        bases[line["_column"]].append(line["x0"])
    margins = {column: min(xs) for column, xs in bases.items()}
    labels = [_label(line) for line in lines]
    labelled = any(match and match[1] for match in labels) or any(
        match and match[2] == "1" for match in labels
    )
    wrap_gap = _wrap_gap(lines)
    groups = []
    for line in lines:
        match = _label(line)
        prior = groups[-1][-1] if groups else None
        new = (
            bool(match) and (bool(match[1]) or int(match[2]) <= len(lines))
            if labelled
            else line["x0"] <= margins[line["_column"]] + 2
        )
        if (
            not labelled
            and prior
            and line["page"] == prior["page"]
            and line["_column"] == prior["_column"]
        ):
            if abs(line["x0"] - prior["x0"]) < 2 and line["top"] - prior["bottom"] < wrap_gap:
                new = False
        if not groups or new:
            groups.append([])
        groups[-1].append(line)
    return groups
